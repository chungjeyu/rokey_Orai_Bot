#!/usr/bin/env python3 수정 후
# ==========================================================
# Node C : YOLO + Depth + Nav2 접근 제어 노드 (robot8 TF 수정본)
# ----------------------------------------------------------
# 수정 사항
# 1. /robot8/tf 직접 구독
# 2. /robot8/tf_static 직접 구독
# 3. /robot8/navigate_to_pose 사용
# 4. 기존 로직 유지
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


# ==========================================================
# Topic / Frame 설정
# ==========================================================

DETECT_TOPIC = '/robot8/detection'
DEPTH_TOPIC = '/robot8/oakd/stereo/image_raw'
CAMERA_INFO_TOPIC = '/robot8/oakd/stereo/camera_info'

SERVICE_NAME = '/robot8/approach_control'

MAP_FRAME = 'map'
BASE_FRAME = 'base_link'


# ==========================================================
# Main Node
# ==========================================================

class NodeCNavApproach(Node):

    def __init__(self):
        super().__init__('node_c_nav_approach')

        # --------------------------------------------------
        # 상태 변수
        # --------------------------------------------------
        self.active = False

        self.bridge = CvBridge()

        self.K = None
        self.depth_img = None
        self.depth_stamp = None
        self.camera_frame = None

        self.latest_uv = None

        self.w = None
        self.h = None

        self.goal_handle = None
        self.last_goal_time = None

        self.processing = False
        self.lock = threading.Lock()

        # --------------------------------------------------
        # 파라미터
        # --------------------------------------------------
        self.stop_offset = 0.30
        self.depth_window = 2
        self.min_depth = 0.2
        self.max_depth = 5.0
        self.goal_cooldown = 2.0

        # --------------------------------------------------
        # TF
        # --------------------------------------------------
        self.tf_buffer = tf2_ros.Buffer()

        self.tf_listener = tf2_ros.TransformListener(
            self.tf_buffer,
            self,
            spin_thread=True
        )

        # # robot8 TF 직접 구독
        # self.create_subscription(
        #     TFMessage,
        #     '/robot8/tf',
        #     self.tf_buffer._tf_callback,
        #     100
        # )

        # self.create_subscription(
        #     TFMessage,
        #     '/robot8/tf_static',
        #     self.tf_buffer._tf_static_callback,
        #     100
        # )

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
            10
        )

        self.create_subscription(
            Image,
            DEPTH_TOPIC,
            self.depth_callback,
            10
        )

        self.create_subscription(
            CameraInfo,
            CAMERA_INFO_TOPIC,
            self.camera_info_callback,
            10
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
        # Timer
        # --------------------------------------------------
        self.create_timer(
            0.2,
            self.process
        )

        self.get_logger().info(
            'Node C READY'
        )

    # ======================================================
    # Service
    # ======================================================

    def handle_service(self, request, response):

        self.get_logger().info(
            f'Service request received: {request.data}'
        )

        if request.data:
            self.active = True
            response.success = True
            response.message = 'Tracking enabled'

            self.get_logger().info(
                'Approach START'
            )

        else:
            self.active = False

            if self.goal_handle:
                try:
                    self.goal_handle.cancel_goal_async()
                except:
                    pass

            response.success = True
            response.message = 'Tracking disabled'

            self.get_logger().info(
                'Approach STOP'
            )

        return response

    # ======================================================
    # Detection
    # ======================================================

    def detect_callback(self, msg):

        self.latest_uv = (
            int(msg.point.x),
            int(msg.point.y)
        )

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
    # Depth
    # ======================================================

    def depth_callback(self, msg):

        if self.K is None:
            return

        self.depth_img = self.bridge.imgmsg_to_cv2(
            msg,
            'passthrough'
        )

        self.depth_stamp = msg.header.stamp
        self.camera_frame = msg.header.frame_id

        self.h, self.w = self.depth_img.shape[:2]

    # ======================================================
    # Depth 추출
    # ======================================================

    def get_depth(self, u, v):

        r = self.depth_window

        u0 = max(0, u - r)
        u1 = min(self.w, u + r + 1)

        v0 = max(0, v - r)
        v1 = min(self.h, v + r + 1)

        region = self.depth_img[v0:v1, u0:u1]

        valid = region[region > 0]

        if valid.size == 0:
            return None

        z = float(np.median(valid))

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
        pt.header.stamp = self.depth_stamp

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

        if self.processing:
            return

        with self.lock:
            self.processing = True

        try:
            if not self.active:
                return

            if self.latest_uv is None:
                return

            if self.depth_img is None:
                return

            if self.K is None:
                return

            u, v = self.latest_uv

            if not (0 <= u < self.w and 0 <= v < self.h):
                return

            z = self.get_depth(u, v)

            if z is None:
                return

            x, y, z = self.pixel_to_3d(u, v, z)

            pt_map = self.transform_to_map(x, y, z)

            target_x = pt_map.point.x
            target_y = pt_map.point.y

            tf = self.tf_buffer.lookup_transform(
                MAP_FRAME,
                BASE_FRAME,
                self.depth_stamp,
                timeout=Duration(seconds=0.3)
            )

            robot_x = tf.transform.translation.x
            robot_y = tf.transform.translation.y

            dist = math.hypot(
                target_x - robot_x,
                target_y - robot_y
            )

            if dist < self.stop_offset:
                self.get_logger().info(
                    'Target reached'
                )
                return

            yaw = math.atan2(
                target_y - robot_y,
                target_x - robot_x
            )

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


# ==========================================================
# MAIN
# ==========================================================

def main(args=None):

    rclpy.init(args=args)

    node = NodeCNavApproach()

    executor = MultiThreadedExecutor(
        num_threads=4
    )

    executor.add_node(node)

    try:
        executor.spin()

    except KeyboardInterrupt:
        pass

    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

