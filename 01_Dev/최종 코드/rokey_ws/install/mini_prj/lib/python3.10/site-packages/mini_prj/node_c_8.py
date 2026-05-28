#!/usr/bin/env python3
# ==========================================================
# Node C : YOLO + Depth + Nav2 접근 제어 노드 (개선판)
# ----------------------------------------------------------
# 주요 개선 사항
# 1. MultiThreadedExecutor 적용
# 2. Nav2 wait_for_server timeout 적용
# 3. Service 응답 안정화
# 4. process() 재진입 방지
# 5. 로그 강화
# ==========================================================


import math
import threading
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor


from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, PoseStamped
from cv_bridge import CvBridge


import tf2_ros
import tf2_geometry_msgs
from tf2_msgs.msg import TFMessage


from nav2_msgs.action import NavigateToPose
from std_srvs.srv import SetBool
from rclpy.time import Time

from rclpy.qos import qos_profile_sensor_data




# ==========================================================
# Topic / Frame 설정
# ==========================================================


DETECT_TOPIC = '/robot8/detection'
DEPTH_TOPIC = '/robot8/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot8/oakd/stereo/camera_info'

SERVICE_NAME = '/robot8/node_c_enable'

MAP_FRAME = 'map'
BASE_FRAME = 'base_link'
DEPTH_W = 704
DEPTH_H = 704
RGB_W = 300
RGB_H = 300


# ==========================================================
# Main Node
# ==========================================================


class NodeCNavApproach(Node):


    def __init__(self):
        super().__init__('node_c_nav_approach')


        # --------------------------------------------------
        # 상태 변수
        # --------------------------------------------------
        self.active = True  # node_a로 부터 서비스 Disable
        # self.active = False # node_a로 부터 서비스 Enable

        self.bridge = CvBridge()

        self.target_reached = False
        self.canceling_goal = False

        self.K = None
        self.depth_img = None
        self.depth_stamp = None
        self.camera_frame = None


        self.latest_uv = None


        self.w = None
        self.h = None


        self.goal_handle = None
        self.last_goal_time = None


        # process 재진입 방지
        self.processing = False
        self.lock = threading.Lock()


        # --------------------------------------------------
        # 튜닝 파라미터
        # --------------------------------------------------
        self.stop_offset = 0.3
        self.depth_window = 2
        self.min_depth = 0.2
        self.max_depth = 5.0
        self.goal_cooldown = 0.5


        # --------------------------------------------------
        # TF
        # --------------------------------------------------
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(
            self.tf_buffer,
            self,
            spin_thread=True
        )

        self.get_logger().info(
            'TF connected : /robot8/tf'
        )

        # --------------------------------------------------
        # Subscriber
        # --------------------------------------------------
        self.create_subscription(
            PointStamped,
            DETECT_TOPIC,
            self.detect_callback,
            qos_profile_sensor_data
        )


        self.create_subscription(
            Image,
            DEPTH_TOPIC,
            self.depth_callback,
            qos_profile_sensor_data
        )


        self.create_subscription(
            CameraInfo,
            CAMERA_INFO_TOPIC,
            self.camera_info_callback,
            qos_profile_sensor_data
        )
        
        # --------------------------------------------------
        # Service
        # --------------------------------------------------
        self.create_service(
            SetBool,
            SERVICE_NAME,
            self.handle_service
        )

        # --------------------------------------------------
        # Nav2 Action Client
        # --------------------------------------------------
        self.nav_client = ActionClient(
            self,
            NavigateToPose,
            '/robot8/navigate_to_pose'
        )

        self.get_logger().info(
            'Waiting for Nav2 action server...'
        )

        if self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().info(
                'Nav2 action server connected'
            )
        else:
            self.get_logger().warn(
                'Nav2 action server not ready yet'
            )

        # --------------------------------------------------
        # Main Timer
        # --------------------------------------------------
        self.create_timer(0.1, self.process)


        self.get_logger().info('Node C READY')

    # ======================================================
    # Service
    # ======================================================

    def handle_service(self, request, response):

        self.get_logger().info(
            f'Service request received: {request.data}'
        )

        if request.data:
            self.active = True
            self.target_reached = False
            self.canceling_goal = False

            response.success = True
            response.message = 'Tracking enabled'

            self.get_logger().info(
                'Approach START'
            )

        else:
            self.active = False
            self.target_reached = False
            self.canceling_goal = False

            if self.goal_handle:
                try:
                    self.goal_handle.cancel_goal_async()
                except:
                    pass
            
            self.goal_handle = None

            response.success = True
            response.message = 'Tracking disabled'

            self.get_logger().info(
                'Approach STOP'
            )

        return response
    
    # ======================================================
    # Detection Callback
    # ======================================================


    def detect_callback(self, msg):
        self.latest_uv = (int(msg.point.x), int(msg.point.y))
        u_rgb, v_rgb = self.latest_uv
        u = int(u_rgb * DEPTH_W / RGB_W)
        v = int(v_rgb * DEPTH_H / RGB_H)
        # self.get_logger().info(f"RGB: ({u_rgb},{v_rgb}) → Depth: ({u},{v})")

        # 범위 체크
        if not (0 <= u < DEPTH_W and 0 <= v < DEPTH_H):
            self.get_logger().warn("uv out of range after scaling")
            return
        
    # ======================================================
    # Camera Info
    # ======================================================


    def camera_info_callback(self, msg):


        if self.K is None:
            self.K = np.array(msg.k).reshape(3, 3)


            self.get_logger().info(
                'Camera info received'
            )


    # ======================================================
    # Depth Callback
    # ======================================================


    def depth_callback(self, msg):
        if self.K is None:
            return
        # self.get_logger().info("Detection topic alive")
        self.depth_img = self.bridge.imgmsg_to_cv2(msg, 'passthrough')
        self.depth_stamp = msg.header.stamp
        self.camera_frame = msg.header.frame_id
        self.h, self.w = self.depth_img.shape[:2]
        # self.get_logger().info(f"Depth received: shape={self.depth_img.shape}")


# ======================================================
    # Depth 추출 (최소 수정판)
    # ======================================================
    def get_depth(self, u, v):
        
        # 1. 윈도우 크기 축소: 배경이 섞일 확률 자체를 낮춤 (기존 4 -> 2로 변경)
        # 5x5 (총 25픽셀) 영역만 타겟팅합니다.
        r = 2 

        u0 = max(0, u - r)
        u1 = min(self.w, u + r + 1)
        v0 = max(0, v - r)
        v1 = min(self.h, v + r + 1)

        region = self.depth_img[v0:v1, u0:u1]
        valid = region[np.isfinite(region) & (region > 0)]

        if valid.size == 0:
            return None

        # 2. 핵심 변경: np.median 대신 하위 20% (Percentile) 사용
        # 배경(먼 거리) 데이터가 섞여 들어와도, 수집된 픽셀 중 가까운 쪽 상위 20%의 거리값을 선택합니다.
        # np.min()을 쓰면 노이즈(먼지 등)에 취약해지므로 20% 정도가 가장 안정적입니다.
        z = float(np.percentile(valid, 20))

        if self.depth_img.dtype == np.uint16:
            z /= 1000.0

        if z < self.min_depth or z > self.max_depth:
            return None

        return z

    # ======================================================
    # Pixel -> 3D
    # ======================================================


    def pixel_to_3d(self, u, v, z):


        fx = self.K[0, 0]
        fy = self.K[1, 1]
        cx = self.K[0, 2]
        cy = self.K[1, 2]


        x = (u - cx) * z / fx
        y = (v - cy) * z / fy


        return x, y, z


    # ======================================================
    # Camera -> Map
    # ======================================================


    def transform_to_map(self, x, y, z):


        pt = PointStamped()


        pt.header.frame_id = self.camera_frame
        pt.header.stamp = Time().to_msg()


        pt.point.x = float(x)
        pt.point.y = float(y)
        pt.point.z = float(z)


        return self.tf_buffer.transform(
            pt,
            MAP_FRAME,
            timeout=Duration(seconds=0.3)
        )    
   
    # ======================================================
    # Main Process
    # ======================================================


    def process(self):

        # self.get_logger().info("processing..")
        # 재진입 방지
        if self.processing:
            return

        with self.lock:
            self.processing = True

        try:
            if not self.active:
                # self.get_logger().info("inactive")
                return

            if self.target_reached:
                return
        
            if self.latest_uv is None:
                # self.get_logger().info("no uv")
                return


            if self.depth_img is None:
                # self.get_logger().info("no depth")
                return


            if self.K is None:
                # self.get_logger().info("no camera info")
                return
           
            u_rgb, v_rgb = self.latest_uv
            u = int(u_rgb * DEPTH_W / RGB_W)
            v = int(v_rgb * DEPTH_H / RGB_H)

            if not (0 <= u < self.w and 0 <= v < self.h):
                # self.get_logger().warn("uv out of range")
                return
           
            z = self.get_depth(u, v)
            # self.get_logger().info(f"pixel u: {u}, v: {v}, depth z: {z}")

            if z is None:
                return

            x, y, z = self.pixel_to_3d(u, v, z)

            try:
                x = x/2
            except Exception as e:
                self.get_logger().warn(f"zero division error: {str(e)}")
                return
            
            pt_map = self.transform_to_map(x, y, z)

            target_x = pt_map.point.x
            target_y = pt_map.point.y

            tf = self.tf_buffer.lookup_transform(
                MAP_FRAME,
                BASE_FRAME,
                Time(),
                timeout=Duration(seconds=0.3)
            )

            robot_x = tf.transform.translation.x
            robot_y = tf.transform.translation.y

            dist = math.hypot(
                target_x - robot_x,
                target_y - robot_y
            )

            if dist < self.stop_offset:
                self.get_logger().info('Target reached -> cancel current goal')

                self.target_reached = True

                if self.goal_handle is not None and not self.canceling_goal:
                    try:
                        self.canceling_goal = True
                        self.goal_handle.cancel_goal_async()
                        self.get_logger().info('Current Nav2 goal canceled')
                    except Exception as e:
                        self.get_logger().warn(f'Failed to cancel goal: {str(e)}')

                # self.goal_handle = None
                return

            yaw = math.atan2(
                target_y - robot_y,
                target_x - robot_x
            )
#=======================================================
            goal = PoseStamped()

            goal.header.frame_id = MAP_FRAME
            goal.header.stamp = self.get_clock().now().to_msg()

            goal.pose.position.x = (
                target_x - self.stop_offset * math.cos(yaw)
            )

            goal.pose.position.y = (
                target_y - self.stop_offset * math.sin(yaw)
            )

            goal.pose.orientation.z = math.sin(yaw / 2.0)
            goal.pose.orientation.w = math.cos(yaw / 2.0)

            now = self.get_clock().now()

            if self.last_goal_time:
                dt = (
                    now - self.last_goal_time
                ).nanoseconds / 1e9

                if dt < self.goal_cooldown:
                    return

            goal_msg = NavigateToPose.Goal()
            goal_msg.pose = goal

            if not self.nav_client.server_is_ready():
                self.get_logger().warn('Nav2 action server is not ready')
                return

            future = self.nav_client.send_goal_async(
                goal_msg
            )

            future.add_done_callback(
                self.goal_response_callback
            )

            self.last_goal_time = now

            self.get_logger().info(
                f'Goal sent ({goal.pose.position.x:.2f}, '
                f'{goal.pose.position.y:.2f})'
            )

        except Exception as e:
            self.get_logger().warn(
                f'Process error: {str(e)}'
            )

        finally:
            self.processing = False

    # ======================================================
    # Action Callbacks
    # ======================================================

    def goal_response_callback(self, future):

        self.goal_handle = future.result()

        if not self.goal_handle.accepted:
            self.get_logger().warn(
                'Goal rejected'
            )
            self.goal_handle = None
            self.canceling_goal = False
            return

        self.get_logger().info(
            'Goal accepted'
        )

        result_future = self.goal_handle.get_result_async()
        result_future.add_done_callback(
            self.goal_result_callback
        )

    def goal_result_callback(self, future):

        self.get_logger().info(
            'Goal finished'
        )
        self.goal_handle = None
        self.canceling_goal = False


# ==========================================================
# MAIN
# ==========================================================

def main():
    rclpy.init()
    node = NodeCNavApproach()

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    executor.spin()

    node.destroy_node()
    rclpy.shutdown()



if __name__ == '__main__':
    main()




