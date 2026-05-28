#!/usr/bin/env python3

import math
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.time import Time
from rclpy.duration import Duration
from rclpy.action import ActionClient

from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, PoseStamped
from nav2_msgs.action import NavigateToPose
from cv_bridge import CvBridge

import tf2_ros
import tf2_geometry_msgs  # noqa: F401
from rclpy.qos import qos_profile_sensor_data


MAP_FRAME = 'map'
BASE_FRAME = 'base_link'

# YOLO 노드 RGB preview 해상도 기준
RGB_W = 300
RGB_H = 300

# # 추종 파라미터
# STOP_OFFSET = 0.8              # 목표 차량과 유지할 거리
# GOAL_UPDATE_THRESHOLD = 0.25   # 새 goal이 25cm 이상 바뀔 때만 갱신
# DISTANCE_TOLERANCE = 0.15      # 목표 거리 근처 허용 오차
# TIMER_PERIOD = 0.1             # 10Hz

STOP_OFFSET = 0.35             # RC카와 약 35cm 거리 유지
GOAL_UPDATE_THRESHOLD = 0.12   # goal이 12cm 이상 바뀔 때만 갱신
DISTANCE_TOLERANCE = 0.08      # ±8cm 허용
TIMER_PERIOD = 0.1             # 10Hz


class FollowTargetNode(Node):
    def __init__(self):
        super().__init__('follow_target_node')

        self.bridge = CvBridge()

        # ==============================
        # 내부 상태
        # ==============================
        self.K = None
        self.depth_img = None
        self.depth_h = None
        self.depth_w = None

        self.latest_uv_msg = None   # YOLO 노드가 보낸 PointStamped
        self.last_goal_x = None
        self.last_goal_y = None

        self.stop_offset = STOP_OFFSET
        self.goal_update_threshold = GOAL_UPDATE_THRESHOLD
        self.distance_tolerance = DISTANCE_TOLERANCE
        self.min_depth = 0.2
        self.max_depth = 10.0

        self.current_goal_handle = None

        # ==============================
        # TF
        # ==============================
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # ==============================
        # Nav2 Action Client
        # ==============================
        self.nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # ==============================
        # Subscribers
        # ==============================
        # 1) YOLO 노드가 주는 중심점 u,v
        self.sub_detection = self.create_subscription(
            PointStamped,
            '/robot4/detection',
            self.detection_callback,
            qos_profile_sensor_data
        )

        # 2) Depth image
        self.sub_depth = self.create_subscription(
            Image,
            '/robot4/oakd/stereo/image_raw',
            self.depth_callback,
            qos_profile_sensor_data
        )

        # 3) Camera info
        self.sub_camera_info = self.create_subscription(
            CameraInfo,
            '/robot4/oakd/stereo/camera_info',
            self.camera_info_callback,
            qos_profile_sensor_data
        )

        # ==============================
        # Timer
        # ==============================
        self.timer = self.create_timer(TIMER_PERIOD, self.timer_callback)

        self.get_logger().info('FollowTargetNode initialized.')

    # =========================================================
    # CALLBACKS
    # =========================================================
    def detection_callback(self, msg: PointStamped):
        """
        YOLO 노드가 publish한 중심점(u,v) 수신
        msg.point.x = u
        msg.point.y = v
        msg.header.frame_id = RGB camera frame
        msg.header.stamp = RGB image stamp
        """
        self.latest_uv_msg = msg

    def depth_callback(self, msg: Image):
        """
        Depth 이미지 수신
        """
        try:
            self.depth_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            self.depth_h, self.depth_w = self.depth_img.shape[:2]
        except Exception as e:
            self.get_logger().warn(f'depth_callback failed: {e}')

    def camera_info_callback(self, msg: CameraInfo):
        """
        Camera intrinsic matrix 저장
        """
        try:
            self.K = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        except Exception as e:
            self.get_logger().warn(f'camera_info_callback failed: {e}')

    def timer_callback(self):
        try:
            self.process()
        except Exception as e:
            self.get_logger().warn(f'process failed: {e}')

    # =========================================================
    # CORE FUNCTIONS
    # =========================================================
    def get_depth(self, u, v):
        """
        중심 주변 작은 window에서 유효한 depth를 모아
        가까운 쪽 percentile을 사용
        """
        if self.depth_img is None or self.depth_w is None or self.depth_h is None:
            return None

        r = 2  # 5x5 window
        u0 = max(0, u - r)
        u1 = min(self.depth_w, u + r + 1)
        v0 = max(0, v - r)
        v1 = min(self.depth_h, v + r + 1)

        region = self.depth_img[v0:v1, u0:u1]
        valid = region[np.isfinite(region) & (region > 0)]

        if valid.size == 0:
            return None

        z = float(np.percentile(valid, 20))

        # uint16 depth면 mm -> m
        if self.depth_img.dtype == np.uint16:
            z /= 1000.0

        if z < self.min_depth or z > self.max_depth:
            return None

        return z

    def pixel_to_3d(self, u, v, z):
        """
        depth optical frame 기준 3D 점 계산
        """
        fx = self.K[0, 0]
        fy = self.K[1, 1]
        cx = self.K[0, 2]
        cy = self.K[1, 2]

        x = (u - cx) * z / fx
        y = (v - cy) * z / fy

        return x, y, z

    def transform_to_map(self, x, y, z):
        """
        카메라 좌표계 점을 map 좌표계로 변환
        camera_info / depth 기준 프레임을 사용해야 함
        """
        pt = PointStamped()
        pt.header.frame_id = 'oakd_stereo_camera_optical_frame'
        pt.header.stamp = Time().to_msg()
        pt.point.x = float(x)
        pt.point.y = float(y)
        pt.point.z = float(z)

        return self.tf_buffer.transform(
            pt,
            MAP_FRAME,
            timeout=Duration(seconds=0.3)
        )

    def get_robot_position(self):
        tf = self.tf_buffer.lookup_transform(
            MAP_FRAME,
            BASE_FRAME,
            Time(),
            timeout=Duration(seconds=0.3)
        )

        robot_x = tf.transform.translation.x
        robot_y = tf.transform.translation.y
        return robot_x, robot_y

    def send_goal(self, goal_pose: PoseStamped):
        if not self.nav_client.server_is_ready():
            self.get_logger().warn('Nav2 action server is not ready')
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = goal_pose

        future = self.nav_client.send_goal_async(goal_msg)
        future.add_done_callback(self.goal_response_callback)

        self.get_logger().info(
            f'Goal sent: ({goal_pose.pose.position.x:.2f}, '
            f'{goal_pose.pose.position.y:.2f})'
        )

    def goal_response_callback(self, future):
        try:
            goal_handle = future.result()
        except Exception as e:
            self.get_logger().warn(f'goal response failed: {e}')
            return

        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn('Goal rejected')
            return

        self.current_goal_handle = goal_handle
        self.get_logger().info('Goal accepted')

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.goal_result_callback)

    def goal_result_callback(self, future):
        try:
            result = future.result()
            self.get_logger().info(f'Goal finished with status: {result.status}')
        except Exception as e:
            self.get_logger().warn(f'goal result callback failed: {e}')

    # =========================================================
    # MAIN PROCESS
    # =========================================================
    def process(self):
        # 필수 데이터 체크
        if self.latest_uv_msg is None:
            return
        if self.K is None:
            return
        if self.depth_img is None:
            return

        # YOLO 노드가 RGB 300x300 preview 기준 중심점 publish
        u_rgb = int(self.latest_uv_msg.point.x)
        v_rgb = int(self.latest_uv_msg.point.y)

        # depth 해상도로 변환
        u = int(u_rgb * self.depth_w / RGB_W)
        v = int(v_rgb * self.depth_h / RGB_H)

        if not (0 <= u < self.depth_w and 0 <= v < self.depth_h):
            self.get_logger().warn(f'uv out of range: ({u}, {v})')
            return

        # depth 추출
        z = self.get_depth(u, v)
        if z is None:
            return

        # 3D 복원
        x, y, z = self.pixel_to_3d(u, v, z)

        # map 좌표 변환
        pt_map = self.transform_to_map(x, y, z)
        target_x = pt_map.point.x
        target_y = pt_map.point.y

        # 현재 로봇 위치
        robot_x, robot_y = self.get_robot_position()

        # 로봇-타겟 중심 간 거리
        dist = math.hypot(
            target_x - robot_x,
            target_y - robot_y
        )

        # 너무 가까우면 새 goal 보내지 않음
        if dist <= (self.stop_offset + self.distance_tolerance):
            self.get_logger().debug(
                f'Close enough: dist={dist:.2f}'
            )
            return

        # 로봇 -> 타겟 방향
        yaw = math.atan2(
            target_y - robot_y,
            target_x - robot_x
        )

        # 목표 차량과 일정 거리 유지한 추종점
        new_goal_x = target_x - self.stop_offset * math.cos(yaw)
        new_goal_y = target_y - self.stop_offset * math.sin(yaw)

        # 이전 goal과 비교해서 충분히 바뀌었을 때만 갱신
        if self.last_goal_x is not None and self.last_goal_y is not None:
            goal_shift = math.hypot(
                new_goal_x - self.last_goal_x,
                new_goal_y - self.last_goal_y
            )

            if goal_shift < self.goal_update_threshold:
                return

        # goal pose 작성
        goal = PoseStamped()
        goal.header.frame_id = MAP_FRAME
        goal.header.stamp = self.get_clock().now().to_msg()

        goal.pose.position.x = new_goal_x
        goal.pose.position.y = new_goal_y
        goal.pose.position.z = 0.0

        # yaw -> quaternion
        goal.pose.orientation.x = 0.0
        goal.pose.orientation.y = 0.0
        goal.pose.orientation.z = math.sin(yaw / 2.0)
        goal.pose.orientation.w = math.cos(yaw / 2.0)

        # 전송
        self.send_goal(goal)

        # 마지막 goal 저장
        self.last_goal_x = new_goal_x
        self.last_goal_y = new_goal_y


def main(args=None):
    rclpy.init(args=args)
    node = FollowTargetNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()