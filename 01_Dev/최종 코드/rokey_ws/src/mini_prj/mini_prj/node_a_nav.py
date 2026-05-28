#!/usr/bin/env python3

import rclpy
import math
from rclpy.node import Node
from std_msgs.msg import Bool

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Directions, TurtleBot4Navigator

class NodeAController(Node):
    """
    다른 PC의 webcam node가 /car_detected(True) publish 하면
    waypoint patrol 시작하는 NodeA
    """

    def __init__(self):
        super().__init__('node_a_controller')

        # 상태 변수
        self.start_requested = False
        self.started = False

        # Subscriber
        self.sub = self.create_subscription(
            Bool,
            'webcam/car_detected',
            self.detect_callback,
            10
        )

        self.get_logger().info('NodeA 대기 중... (/car_detected True 기다리는 중)')

        # Turtlebot Navigator
        self.navigator = TurtleBot4Navigator(namespace='/robot8')

    # --------------------------------------------------
    # webcam node 에서 차량 감지 시 호출
    # --------------------------------------------------
    def detect_callback(self, msg):
        if msg.data and not self.started:
            self.get_logger().info('차량 감지 신호 수신! waypoint patrol 시작')
            self.start_requested = True

    # --------------------------------------------------
    # 메인 patrol 실행
    # --------------------------------------------------
    def execute_mission(self):

        self.started = True

        # Dock 상태 확인
        if not self.navigator.getDockedStatus():
            self.navigator.info('Docking before initializing pose')
            self.navigator.dock()

        # Initial Pose
        initial_pose = self.navigator.getPoseStamped(
            [0.0, 0.0],
            TurtleBot4Directions.NORTH
        )
        self.navigator.setInitialPose(initial_pose)

        # Nav2 활성화 대기
        self.navigator.waitUntilNav2Active()

        # 웨이포인트 설정
        goal_pose = []

        goal_pose.append(
            self.navigator.getPoseStamped(
                [-0.1668, -0.3049],
                TurtleBot4Directions.SOUTH
            )
        )

        goal_pose.append(
            self.navigator.getPoseStamped(
                [-1.1943, -0.3740],
                TurtleBot4Directions.SOUTH
            )
        )

        goal_pose.append(
            self.navigator.getPoseStamped(
                [-1.5589, 1.7090],
                TurtleBot4Directions.NORTH
            )
        )

        goal_pose.append(
            self.navigator.getPoseStamped(
                [-0.4276, 1.8617],
                TurtleBot4Directions.NORTH
            )
        )

        # Undock
        self.navigator.undock()

        # ------------------------------------------
        # Waypoint 순찰 + 회전
        # ------------------------------------------
        for i, pose in enumerate(goal_pose):

            self.navigator.info(
                f'[{i+1}/{len(goal_pose)}] waypoint 이동 중...'
            )

            self.navigator.startToPose(pose)

            while not self.navigator.isTaskComplete():
                rclpy.spin_once(self, timeout_sec=0.1)

            self.navigator.info(
                f'[{i+1}/{len(goal_pose)}] 도착 완료! 360도 회전 시작'
            )

            self.navigator.spin(
                spin_dist=2.0 * math.pi
            )

            while not self.navigator.isTaskComplete():
                rclpy.spin_once(self, timeout_sec=0.1)

        self.navigator.info('모든 waypoint 순찰 완료')


        self.get_logger().info('미션 종료')
        self.started = False
        self.start_requested = False


def main(args=None):
    rclpy.init(args=args)

    node = NodeAController()

    try:
        while rclpy.ok():

            # webcam 에서 True 받으면 시작
            if node.start_requested and not node.started:
                node.execute_mission()

            rclpy.spin_once(node, timeout_sec=0.1)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()