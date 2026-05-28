#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32


class SimpleTrackingController(Node):
    def __init__(self):
        super().__init__('simple_tracking_controller')

        # ==============================
        # Parameters
        # ==============================
        self.declare_parameter('depth_topic', '/robot3/target_depth')
        self.declare_parameter('yaw_topic', '/robot3/target_yaw')
        self.declare_parameter('cmd_vel_topic', '/robot3/cmd_vel')

        self.declare_parameter('timer_period', 0.1)
        self.declare_parameter('target_distance', 0.7)
        self.declare_parameter('distance_tolerance', 0.08)
        self.declare_parameter('safety_stop_distance', 0.35)
        self.declare_parameter('yaw_gate_rad', 0.12)
        self.declare_parameter('data_timeout', 0.5)

        self.declare_parameter('kp_yaw', 1.2)
        self.declare_parameter('kd_yaw', 0.1)
        self.declare_parameter('kp_dist', 0.4)
        self.declare_parameter('kd_dist', 0.0)

        self.declare_parameter('max_linear_speed', 0.12)
        self.declare_parameter('max_angular_speed', 0.6)
        self.declare_parameter('max_linear_accel', 0.08)
        self.declare_parameter('max_angular_accel', 0.15)
        self.declare_parameter('deadband_linear', 0.02)
        self.declare_parameter('deadband_angular', 0.03)

        self.declare_parameter('debug_log', True)

        depth_topic = self.get_parameter('depth_topic').value
        yaw_topic = self.get_parameter('yaw_topic').value
        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value

        self.timer_period = float(self.get_parameter('timer_period').value)
        self.target_distance = float(self.get_parameter('target_distance').value)
        self.distance_tolerance = float(self.get_parameter('distance_tolerance').value)
        self.safety_stop_distance = float(self.get_parameter('safety_stop_distance').value)
        self.yaw_gate_rad = float(self.get_parameter('yaw_gate_rad').value)
        self.data_timeout = float(self.get_parameter('data_timeout').value)

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

        self.debug_log = bool(self.get_parameter('debug_log').value)

        # ==============================
        # Internal state
        # ==============================
        self.current_depth = None
        self.current_yaw = None

        self.last_depth_time = None
        self.last_yaw_time = None

        self.prev_dist_error = 0.0
        self.prev_yaw_error = 0.0

        self.prev_cmd_linear = 0.0
        self.prev_cmd_angular = 0.0

        # ==============================
        # Subscribers
        # ==============================
        self.sub_depth = self.create_subscription(
            Float32,
            depth_topic,
            self.depth_callback,
            10
        )

        self.sub_yaw = self.create_subscription(
            Float32,
            yaw_topic,
            self.yaw_callback,
            10
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

        self.get_logger().info('SimpleTrackingController initialized.')

    # =========================================================
    # Callbacks
    # =========================================================
    def depth_callback(self, msg: Float32):
        self.current_depth = float(msg.data)
        self.last_depth_time = self.get_clock().now()

        if self.debug_log:
            self.get_logger().info(f'[INPUT] depth={self.current_depth:.3f} m')

    def yaw_callback(self, msg: Float32):
        self.current_yaw = float(msg.data)
        self.last_yaw_time = self.get_clock().now()

        if self.debug_log:
            self.get_logger().info(f'[INPUT] yaw={self.current_yaw:.3f} rad')

    # =========================================================
    # Utility
    # =========================================================
    def publish_stop(self, reason=''):
        cmd = Twist()
        self.pub_cmd_vel.publish(cmd)
        self.prev_cmd_linear = 0.0
        self.prev_cmd_angular = 0.0

        if self.debug_log:
            self.get_logger().info(
                f'[CMD] STOP | reason={reason} | vx=0.000, wz=0.000'
            )

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

    def data_is_fresh(self):
        now = self.get_clock().now()

        if self.current_depth is None or self.current_yaw is None:
            return False

        if self.last_depth_time is None or self.last_yaw_time is None:
            return False

        dt_depth = (now - self.last_depth_time).nanoseconds * 1e-9
        dt_yaw = (now - self.last_yaw_time).nanoseconds * 1e-9

        if self.debug_log:
            self.get_logger().info(
                f'[AGE] depth_age={dt_depth:.3f}s | yaw_age={dt_yaw:.3f}s'
            )

        return (dt_depth <= self.data_timeout) and (dt_yaw <= self.data_timeout)

    # =========================================================
    # Main control
    # =========================================================
    def control_loop(self):
        if not self.data_is_fresh():
            self.publish_stop(reason='stale_or_missing_data')
            return

        depth = self.current_depth
        yaw_error = self.current_yaw

        if depth <= 0.0:
            self.publish_stop(reason='invalid_depth')
            return

        dist_error = depth - self.target_distance

        dt = self.timer_period
        ddist = (dist_error - self.prev_dist_error) / dt
        dyaw = (yaw_error - self.prev_yaw_error) / dt

        # yaw PD
        raw_angular_z = self.kp_yaw * yaw_error + self.kd_yaw * dyaw
        angular_z = self.clamp(
            raw_angular_z,
            -self.max_angular_speed,
            self.max_angular_speed
        )

        # distance P/PD
        if depth <= self.safety_stop_distance:
            linear_x = 0.0
            state = 'SAFETY_STOP'

        elif abs(dist_error) <= self.distance_tolerance:
            linear_x = 0.0
            state = 'HOLD'

        elif abs(yaw_error) > self.yaw_gate_rad:
            linear_x = 0.0
            state = 'ALIGN'

        else:
            raw_linear_x = self.kp_dist * dist_error + self.kd_dist * ddist

            if raw_linear_x < 0.0:
                raw_linear_x = 0.0

            linear_x = self.clamp(
                raw_linear_x,
                0.0,
                self.max_linear_speed
            )
            state = 'APPROACH'

        # 로그용 raw 값 보존
        if state != 'APPROACH':
            raw_linear_x = 0.0

        # slew limit
        linear_x = self.slew_limit(
            linear_x,
            self.prev_cmd_linear,
            self.max_linear_accel
        )
        angular_z = self.slew_limit(
            angular_z,
            self.prev_cmd_angular,
            self.max_angular_accel
        )

        # deadband
        linear_x = self.apply_deadband(linear_x, self.deadband_linear)
        angular_z = self.apply_deadband(angular_z, self.deadband_angular)

        # publish
        cmd = Twist()
        cmd.linear.x = float(linear_x)
        cmd.angular.z = float(angular_z)
        self.pub_cmd_vel.publish(cmd)

        # save previous
        self.prev_dist_error = dist_error
        self.prev_yaw_error = yaw_error
        self.prev_cmd_linear = linear_x
        self.prev_cmd_angular = angular_z

        if self.debug_log:
            self.get_logger().info(
                '[CTRL] '
                f'state={state} | depth={depth:.3f} m | yaw={yaw_error:.3f} rad | '
                f'dist_err={dist_error:.3f} | ddist={ddist:.3f} | dyaw={dyaw:.3f} | '
                f'raw_vx={raw_linear_x:.3f} | raw_wz={raw_angular_z:.3f} | '
                f'cmd_vel: vx={linear_x:.3f}, wz={angular_z:.3f}'
            )


def main(args=None):
    rclpy.init(args=args)
    node = SimpleTrackingController()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publish_stop(reason='shutdown')
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()