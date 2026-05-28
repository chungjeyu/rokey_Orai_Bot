#!/usr/bin/env python3
"""
=========================================================
Node A : Mission Manager (Patrol + Search Spin + Handover)
=========================================================

[프로젝트 역할]
외부 webcam PC가 rc_car를 발견하면 순찰 시작.
로봇은 waypoint 순찰을 수행한다.

각 waypoint 도착 후:
    -> 천천히 360도 회전하며 onboard YOLO(NodeB)가 rc_car 탐색

NodeB가 confidence topic을 보내고,
조건 만족 시:

    -> 현재 Nav2 goal 취소
    -> 회전 정지
    -> NodeA 종료 상태(STOP)
    -> 이후 NodeC가 접근 제어 예정

---------------------------------------------------------
[사용 Topic]

입력:
    /webcam/car_detected      (Bool)
    /robot8/confidence       (Float32)

출력:
    /robot8/cmd_vel          (Twist)

---------------------------------------------------------
[중요 설계 포인트]

1. 시작 시 Dock 유지
   - localization 안정화
   - 초기 위치 기준 확보

2. 회전은 navigator.spin() 대신 직접 cmd_vel
   - 느린 회전 가능
   - YOLO 탐지율 향상

3. 미션 종료 후 재시작 방지
   - node_enabled = False

=========================================================
"""

import rclpy
import math
import time

from rclpy.node import Node

from std_msgs.msg import Bool
from geometry_msgs.msg import Twist
from my_interfaces.msg import Detection

from turtlebot4_navigation.turtlebot4_navigator import     TurtleBot4Navigator, TurtleBot4Directions



class NodeAController(Node):

    def __init__(self):
        super().__init__('node_a_controller')

        # -------------------------------------------------
        # 상태 변수
        # -------------------------------------------------

        # webcam trigger 수신 시 mission 시작 요청
        self.start_requested = False
        # mission 실행 중 여부
        self.started = False

        # mission 종료 후 완전 비활성화
        self.node_enabled = True

        # confidence 조건 만족 시 취소 요청
        self.cancel_requested = False

        # -------------------------------------------------
        # YOLO confidence 누적 필터
        # -------------------------------------------------

        self.confidence_counter = 0

        # confidence 2회 연속 이상이면 탐지로 판단
        self.threshold = 3

        # confidence 최소 기준
        self.conf_threshold = 0.70

        # -------------------------------------------------
        # Subscriber : webcam trigger
        # -------------------------------------------------

        self.sub_trigger = self.create_subscription(
            Bool,
            '/webcam/car_detected',
            self.detect_callback,
            10
        )

        # -------------------------------------------------
        # Subscriber : NodeB confidence
        # -------------------------------------------------

        self.sub_conf = self.create_subscription(
            Detection,
            '/robot8/confidence',
            self.confidence_callback,
            10
        )

        # -------------------------------------------------
        # Publisher : 직접 회전 제어용 cmd_vel
        # -------------------------------------------------

        self.cmd_pub = self.create_publisher(
            Twist,
            '/robot8/cmd_vel',
            10
        )

        # -------------------------------------------------
        # Turtlebot4 Navigator
        # -------------------------------------------------

        self.navigator = TurtleBot4Navigator(namespace='/robot8')

        self.get_logger().info('NodeA 준비 완료')
        self.get_logger().info('webcam trigger 대기 중...')

    # =====================================================
    # webcam trigger callback
    # =====================================================

    def detect_callback(self, msg):
        """
        외부 webcam PC가 차량 발견 시 True publish

        True 들어오면 mission 시작 요청
        """

        # mission 종료 후 node 비활성화 상태면 무시
        if not self.node_enabled:
            return

        if msg.data and not self.started:
            self.get_logger().info('차량 감지! Patrol 시작 요청')
            self.start_requested = True

    # =====================================================
    # NodeB confidence callback
    # =====================================================

    def confidence_callback(self, msg):
        """
        onboard YOLO(NodeB)가 confidence publish

        threshold 이상 누적되면:
            cancel_requested = True
        """

        confidence = msg.data

        # mission 중이 아닐 때는 무시
        if not self.started:
            return

        # confidence 누적 로직
        if confidence > self.conf_threshold:
            self.confidence_counter = min(
                10,
                self.confidence_counter + 1
            )
        else:
            self.confidence_counter = max(
                0,
                self.confidence_counter - 1
            )

        # threshold 도달 시 취소 요청
        if self.confidence_counter >= self.threshold:

            # 중복 로그 방지
            if not self.cancel_requested:
                self.get_logger().info(
                    f'목표 탐지 확정 '
                    f'({self.confidence_counter}/{self.threshold})'
                )

            self.cancel_requested = True

    # =====================================================
    # 현재 Nav2 goal 취소
    # =====================================================

    def cancel_current_navigation(self):

        self.get_logger().info('현재 navigation goal 취소 요청')

        self.navigator.cancelTask()

        deadline = time.time() + 3.0

        while rclpy.ok() and time.time() < deadline:

            rclpy.spin_once(self, timeout_sec=0.1)

            if self.navigator.isTaskComplete():
                self.get_logger().info('goal 취소 완료')
                return True

        self.get_logger().warn('goal 취소 timeout')
        return False

    # =====================================================
    # 로봇 완전 정지
    # =====================================================

    def stop_robot(self):
        """
        action cancel + cmd_vel zero
        """

        self.navigator.cancelTask()

        msg = Twist()

        for _ in range(5):
            self.cmd_pub.publish(msg)
            time.sleep(0.05)

    # =====================================================
    # waypoint 도착 후 느린 360도 회전 탐색
    # =====================================================

    def slow_spin_search(self):
        """
        천천히 회전하면서 YOLO 탐색

        빠른 회전은 blur 때문에 탐지율 저하
        """

        self.get_logger().info('천천히 360도 탐색 회전 시작')

        msg = Twist()

        # 회전 속도 (rad/s)
        msg.angular.z = 0.30

        # 회전 시간 계산
        duration = (2.0 * math.pi) / 0.30

        end_time = time.time() + duration

        while rclpy.ok() and time.time() < end_time:

            rclpy.spin_once(self, timeout_sec=0.05)

            # 탐지되면 즉시 종료
            if self.cancel_requested:
                break

            self.cmd_pub.publish(msg)

        # 정지
        msg.angular.z = 0.0
        self.cmd_pub.publish(msg)

        self.get_logger().info('회전 종료')

    # =====================================================
    # Mission Main
    # =====================================================

    def execute_mission(self):

        self.get_logger().info('Mission 시작')

        self.started = True
        self.cancel_requested = False
        self.confidence_counter = 0

        # -------------------------------------------------
        # Dock 상태 확인
        # Dock 기준으로 localization 안정화
        # -------------------------------------------------

        if not self.navigator.getDockedStatus():
            self.navigator.info(
                'Docking before initializing pose'
            )
            self.navigator.dock()

        # -------------------------------------------------
        # Initial Pose
        # -------------------------------------------------

        initial_pose = self.navigator.getPoseStamped(
            [0.0, 0.0],
            TurtleBot4Directions.NORTH
        )

        self.navigator.setInitialPose(initial_pose)

        # -------------------------------------------------
        # Nav2 활성화 대기
        # -------------------------------------------------

        self.navigator.waitUntilNav2Active()

        # -------------------------------------------------
        # waypoint 설정
        # -------------------------------------------------

        goal_pose = [

            self.navigator.getPoseStamped(
                [-0.1668, -0.3049],
                TurtleBot4Directions.SOUTH
            ),

            self.navigator.getPoseStamped(
                [-1.1943, -0.3740],
                TurtleBot4Directions.SOUTH
            ),

            self.navigator.getPoseStamped(
                [-1.5589, 1.7090],
                TurtleBot4Directions.NORTH
            ),

            self.navigator.getPoseStamped(
                [-0.4276, 1.8617],
                TurtleBot4Directions.NORTH
            ),
        ]

        # 출발
        self.navigator.undock()

        # =================================================
        # waypoint patrol 시작
        # =================================================

        for i, pose in enumerate(goal_pose):

            self.get_logger().info(
                f'[{i+1}/{len(goal_pose)}] waypoint 이동'
            )

            self.navigator.startToPose(pose)

            # ---------------------------------------------
            # 이동 중 대기
            # ---------------------------------------------
            while not self.navigator.isTaskComplete():

                rclpy.spin_once(self, timeout_sec=0.1)

                # 목표 탐지되면 취소
                if self.cancel_requested:

                    self.cancel_current_navigation()
                    self.stop_robot()

                    self.get_logger().info(
                        'NodeC에게 제어 이관 예정'
                    )

                    self.finish_mission()
                    return

            # ---------------------------------------------
            # 도착 후 탐색 회전
            # ---------------------------------------------
            self.get_logger().info(
                f'[{i+1}] waypoint 도착'
            )

            self.slow_spin_search()

            # 회전 중 탐지된 경우
            if self.cancel_requested:

                self.stop_robot()

                self.get_logger().info(
                    'NodeC에게 제어 이관 예정'
                )

                self.finish_mission()
                return

        # -------------------------------------------------
        # 모든 waypoint 완료
        # -------------------------------------------------

        self.get_logger().info('모든 waypoint 순찰 완료')

        self.finish_mission()

    # =====================================================
    # Mission 종료 처리
    # =====================================================

    def finish_mission(self):

        self.stop_robot()

        self.started = False
        self.start_requested = False
        self.cancel_requested = False
        self.confidence_counter = 0

        # mission 종료 후 재시작 금지
        self.node_enabled = False

        self.get_logger().info('Mission 종료')
        self.get_logger().info('NodeA STOP 상태')

    # =====================================================
    # main
    # =====================================================


def main(args=None):

    rclpy.init(args=args)

    node = NodeAController()

    try:
        while rclpy.ok():

            # webcam trigger 수신 시 mission 시작
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