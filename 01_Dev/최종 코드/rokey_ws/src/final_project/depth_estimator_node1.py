#!/usr/bin/env python3

import math
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, Twist
from cv_bridge import CvBridge
from rclpy.qos import qos_profile_sensor_data


# YOLO preview 해상도
RGB_W = 704
RGB_H = 704


class VisualTrackingController(Node):
    def __init__(self):
        super().__init__('visual_tracking_controller')

        self.bridge = CvBridge()

        # ==============================
        # Parameters
        # ==============================
        self.declare_parameter('detection_topic', '/robot3/detection')
        self.declare_parameter('depth_topic', '/robot3/oakd/rgb/image_raw/compressedDepth')

        self.declare_parameter('camera_info_topic', '/robot3/oakd/stereo/camera_info')
        self.declare_parameter('cmd_vel_topic', '/robot3/cmd_vel')

        self.declare_parameter('timer_period', 0.1)       # 10 Hz
        self.declare_parameter('target_distance', 0.2)    # 유지 목표 거리
        self.declare_parameter('distance_tolerance', 0.08)
        self.declare_parameter('yaw_gate_rad', 0.15)      # 이보다 yaw 크면 전진 금지
        self.declare_parameter('lost_timeout', 0.5)

        self.declare_parameter('min_depth', 0.2)
        self.declare_parameter('max_depth', 8.0)
        self.declare_parameter('depth_window_radius', 3)

        # PID gains
        self.declare_parameter('kp_yaw', 1.8)
        self.declare_parameter('kd_yaw', 0.15)

        self.declare_parameter('kp_dist', 0.6)
        self.declare_parameter('kd_dist', 0.0)

        # output limits
        self.declare_parameter('max_linear_speed', 0.18)
        self.declare_parameter('max_angular_speed', 0.8)
        self.declare_parameter('max_linear_accel', 0.08)   # m/s per cycle limit 느낌
        self.declare_parameter('max_angular_accel', 0.15)  # rad/s per cycle limit
        self.declare_parameter('deadband_linear', 0.02)
        self.declare_parameter('deadband_angular', 0.03)

        detection_topic = self.get_parameter('detection_topic').value
        depth_topic = self.get_parameter('depth_topic').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value

        self.timer_period = float(self.get_parameter('timer_period').value)
        self.target_distance = float(self.get_parameter('target_distance').value)
        self.distance_tolerance = float(self.get_parameter('distance_tolerance').value)
        self.yaw_gate_rad = float(self.get_parameter('yaw_gate_rad').value)
        self.lost_timeout = float(self.get_parameter('lost_timeout').value)

        self.min_depth = float(self.get_parameter('min_depth').value)
        self.max_depth = float(self.get_parameter('max_depth').value)
        self.depth_window_radius = int(self.get_parameter('depth_window_radius').value)

        self.kp_yaw = float(self.get_parameter('kp_yaw').value)
        self.kd_yaw = float(self.get_parameter('kd_yaw').value)
        self.kp_dist = float(self.get_parameter('kp_dist').value)
        self.kd_dist = float(self.get_parameter('kd_dist').value)

        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)
        self.max_linear_accel = float(self.get_parameter('max_linear_accel').value)
        self.max_angular_accel = float(self.get_parameter('max_angular_accel').value)
        self.deadband_linear = float(self.get_parameter('deadband_linear').value)
        self.deadband_angular = float(self.get_parameter('deadband_angular').value)

        # ==============================
        # Internal state
        # ==============================
        self.K = None
        self.depth_img = None
        self.depth_h = None
        self.depth_w = None

        self.latest_uv_msg = None
        self.last_detection_time = None

        self.prev_yaw_error = 0.0
        self.prev_dist_error = 0.0

        self.prev_cmd_linear = 0.0
        self.prev_cmd_angular = 0.0

        self.filtered_depth = None
        self.depth_alpha = 0.5

        # ==============================
        # Subscribers
        # ==============================
        self.sub_detection = self.create_subscription(
            PointStamped,
            detection_topic,
            self.detection_callback,
            qos_profile_sensor_data
        )

        self.sub_depth = self.create_subscription(
            Image,
            depth_topic,
            self.depth_callback,
            qos_profile_sensor_data
        )

        self.sub_camera_info = self.create_subscription(
            CameraInfo,
            camera_info_topic,
            self.camera_info_callback,
            qos_profile_sensor_data
        )

        # ==============================
        # Publisher
        # ==============================
        self.pub_cmd_vel = self.create_publisher(
            Twist,
            cmd_vel_topic,
            10
        )

        # ==============================
        # Timer
        # ==============================
        self.timer = self.create_timer(self.timer_period, self.control_loop)

        self.get_logger().info('VisualTrackingController initialized.')

    # =========================================================
    # Callbacks
    # =========================================================
    def detection_callback(self, msg: PointStamped):
        self.latest_uv_msg = msg
        self.last_detection_time = self.get_clock().now()
    
    def depth_callback(self, msg: Image):
        try:
            self.depth_img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
            self.depth_h, self.depth_w = self.depth_img.shape[:2]
            self.get_logger().info(f'depth_size, w: {self.depth_w}, h: {self.depth_h}')
        except Exception as e:
            self.get_logger().warn(f'depth_callback failed: {e}')

    def camera_info_callback(self, msg: CameraInfo):
        try:
            self.K = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        except Exception as e:
            self.get_logger().warn(f'camera_info_callback failed: {e}')

    # =========================================================
    # Utility
    # =========================================================
    def publish_stop(self):
        msg = Twist()
        self.pub_cmd_vel.publish(msg)
        self.prev_cmd_linear = 0.0
        self.prev_cmd_angular = 0.0

    def clamp(self, value, min_v, max_v):
        return max(min_v, min(max_v, value))

    def slew_limit(self, target, prev, max_step):
        if target > prev + max_step:
            return prev + max_step
        if target < prev - max_step:
            return prev - max_step
        return target

    def apply_deadband(self, value, threshold):
        return 0.0 if abs(value) < threshold else value

    def get_depth(self, u, v):
        if self.depth_img is None or self.depth_w is None or self.depth_h is None:
            return None

        r = self.depth_window_radius
        u0 = max(0, u - r)
        u1 = min(self.depth_w, u + r + 1)
        v0 = max(0, v - r)
        v1 = min(self.depth_h, v + r + 1)

        region = self.depth_img[v0:v1, u0:u1]
        valid = region[np.isfinite(region) & (region > 0)]

        if valid.size == 0:
            return None

        z = float(np.median(valid))

        if self.depth_img.dtype == np.uint16:
            z /= 1000.0

        if z < self.min_depth or z > self.max_depth:
            return None

        return z

    # =========================================================
    # Main control
    # =========================================================
    def control_loop(self):
        # 필수 데이터 확인
        if self.latest_uv_msg is None or self.K is None or self.depth_img is None:
            self.publish_stop()
            return

        # 검출 timeout
        now = self.get_clock().now()
        if self.last_detection_time is None:
            self.publish_stop()
            return

        dt_lost = (now - self.last_detection_time).nanoseconds * 1e-9
        if dt_lost > self.lost_timeout:
            self.get_logger().debug('Target lost -> stop')
            self.publish_stop()
            return

        # YOLO preview 기준 좌표
        u_rgb = int(self.latest_uv_msg.point.x)
        v_rgb = int(self.latest_uv_msg.point.y)

        # depth 이미지 해상도 기준으로 변환
        u = int(u_rgb * self.depth_w / RGB_W)
        v = int(v_rgb * self.depth_h / RGB_H)

        if not (0 <= u < self.depth_w and 0 <= v < self.depth_h):
            self.publish_stop()
            return

        # depth 측정
        depth = self.get_depth(u, v)
        if depth is None:
            self.publish_stop()
            return

        # depth smoothing
        if self.filtered_depth is None:
            self.filtered_depth = depth
        else:
            self.filtered_depth = self.depth_alpha * depth + (1.0 - self.depth_alpha) * self.filtered_depth

        depth = self.filtered_depth

        # intrinsic
        fx = self.K[0, 0]
        cx = self.K[0, 2]

        # yaw 오차: optical axis 기준 소각도 근사
        yaw_error = math.atan2((u - cx), fx)

        # 거리 오차: 현재 거리 - 목표 거리
        dist_error = depth - self.target_distance

        # derivative
        dt = self.timer_period
        dyaw = (yaw_error - self.prev_yaw_error) / dt
        ddist = (dist_error - self.prev_dist_error) / dt

        # angular.z
        angular_z = self.kp_yaw * yaw_error + self.kd_yaw * dyaw
        angular_z = self.clamp(angular_z, -self.max_angular_speed, self.max_angular_speed)

        # linear.x
        # 1) 너무 가까우면 전진 금지
        # 2) yaw 오차가 크면 전진 금지
        # 3) 목표 거리 근처면 정지
        if abs(dist_error) <= self.distance_tolerance:
            linear_x = 0.0
            state = 'HOLD'
        elif abs(yaw_error) > self.yaw_gate_rad:
            linear_x = 0.0
            state = 'ALIGN'
        else:
            linear_x = self.kp_dist * dist_error + self.kd_dist * ddist

            # 뒤로 가는 추종은 일단 막음
            if linear_x < 0.0:
                linear_x = 0.0

            linear_x = self.clamp(linear_x, 0.0, self.max_linear_speed)
            state = 'APPROACH'

        # slew limit
        linear_x = self.slew_limit(linear_x, self.prev_cmd_linear, self.max_linear_accel)
        angular_z = self.slew_limit(angular_z, self.prev_cmd_angular, self.max_angular_accel)

        # deadband
        linear_x = self.apply_deadband(linear_x, self.deadband_linear)
        angular_z = self.apply_deadband(angular_z, self.deadband_angular)

        # publish
        cmd = Twist()
        cmd.linear.x = float(linear_x)
        cmd.angular.z = float(angular_z)
        self.pub_cmd_vel.publish(cmd)

        # save previous
        self.prev_cmd_linear = linear_x
        self.prev_cmd_angular = angular_z
        self.prev_yaw_error = yaw_error
        self.prev_dist_error = dist_error

        self.get_logger().debug(
            f'state={state}, depth={depth:.2f}, dist_err={dist_error:.2f}, '
            f'yaw_err={yaw_error:.3f}, vx={linear_x:.2f}, wz={angular_z:.2f}'
        )


def main(args=None):
    rclpy.init(args=args)
    node = VisualTrackingController()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publish_stop()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()