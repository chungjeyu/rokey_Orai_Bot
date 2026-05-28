#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32


class FakeTargetPublisher(Node):
    def __init__(self):
        super().__init__('fake_target_publisher')

        # ==============================
        # Parameters
        # ==============================
        self.declare_parameter('depth_topic', '/robot3/target_depth')
        self.declare_parameter('yaw_topic', '/robot3/target_yaw')
        self.declare_parameter('timer_period', 0.1)
        self.declare_parameter('scenario', 'approach')  
        # scenario:
        #   approach      : 멀리서 점점 다가오는 상황
        #   yaw_swing     : 좌우로 흔들리는 yaw
        #   hold_test     : 목표 거리 근처 유지
        #   safety_test   : 너무 가까워지는 상황
        #   mixed         : depth, yaw 둘 다 변함

        depth_topic = self.get_parameter('depth_topic').value
        yaw_topic = self.get_parameter('yaw_topic').value
        self.timer_period = float(self.get_parameter('timer_period').value)
        self.scenario = self.get_parameter('scenario').value

        # ==============================
        # Publishers
        # ==============================
        self.pub_depth = self.create_publisher(Float32, depth_topic, 10)
        self.pub_yaw = self.create_publisher(Float32, yaw_topic, 10)

        # ==============================
        # Internal state
        # ==============================
        self.t = 0.0

        # ==============================
        # Timer
        # ==============================
        self.timer = self.create_timer(self.timer_period, self.timer_callback)

        self.get_logger().info(
            f'FakeTargetPublisher initialized. scenario={self.scenario}'
        )

    def timer_callback(self):
        depth = 1.2
        yaw = 0.0

        # --------------------------------------
        # 시나리오별 depth / yaw 생성
        # --------------------------------------
        if self.scenario == 'approach':
            # 멀리서 출발해서 서서히 가까워짐
            depth = max(0.25, 1.5 - 0.05 * self.t)
            yaw = 0.02 * math.sin(0.8 * self.t)

        elif self.scenario == 'yaw_swing':
            # 거리는 일정, yaw만 좌우 흔들림
            depth = 0.9
            yaw = 0.35 * math.sin(1.2 * self.t)

        elif self.scenario == 'hold_test':
            # 목표 거리 근처에서 작은 노이즈
            depth = 0.7 + 0.03 * math.sin(1.5 * self.t)
            yaw = 0.03 * math.sin(1.0 * self.t)

        elif self.scenario == 'safety_test':
            # 점점 가까워져서 safety_stop 거리 안으로 들어감
            depth = max(0.15, 0.8 - 0.06 * self.t)
            yaw = 0.01 * math.sin(self.t)

        elif self.scenario == 'mixed':
            # depth, yaw 둘 다 변함
            depth = 0.8 + 0.4 * math.sin(0.35 * self.t)
            yaw = 0.22 * math.sin(0.9 * self.t)

        else:
            # fallback
            depth = 1.0
            yaw = 0.0

        # publish
        depth_msg = Float32()
        depth_msg.data = float(depth)

        yaw_msg = Float32()
        yaw_msg.data = float(yaw)

        self.pub_depth.publish(depth_msg)
        self.pub_yaw.publish(yaw_msg)

        self.get_logger().info(
            f'[FAKE PUB] t={self.t:.1f}s | depth={depth:.3f} m | yaw={yaw:.3f} rad'
        )

        self.t += self.timer_period


def main(args=None):
    rclpy.init(args=args)
    node = FakeTargetPublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()