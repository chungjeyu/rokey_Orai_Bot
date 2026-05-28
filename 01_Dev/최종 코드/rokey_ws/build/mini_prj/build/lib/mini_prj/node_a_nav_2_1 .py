#!/usr/bin/env python3

import rclpy
import math
import time

from rclpy.node import Node
from std_msgs.msg import Bool, Float32
from my_interfaces.msg import Detection
from geometry_msgs.msg import Twist
from std_srvs.srv import SetBool

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Directions, TurtleBot4Navigator

class NodeAController(Node):
    """
    다른 PC의 webcam node가 /car_detected(True) publish 하면
    waypoint patrol 시작하는 NodeA
    """

    def __init__(self):
        super().__init__('node_a_controller')

        # -------------------------------------------------
        # YOLO confidence 누적 필터
        # -------------------------------------------------
        self.confidence_counter = 0
        self.threshold = 2
        self.conf_threshold = 0.7

        # -------------------------------------------------
        # 상태 변수
        # -------------------------------------------------
        self.start_requested = False       # webcam trigger 수신 시 mission 시작 요청
        self.started = False               # mission 실행 중 여부

        self.node_enabled = True           # mission 종료 후 완전 비활성화

        self.cancel_requested = False      # confidence 조건 만족 시 취소 요청

        self.node_c_requested = False      # confidence 조건 만족 후 Node C 제어 이관 요청 (중복 방지) 

        # -------------------------------------------------
        # Subscriber : webcam trigger
        # -------------------------------------------------
        self.sub = self.create_subscription(
            Bool,
            'webcam/car_detected',
            self.detect_callback,
            10
        )

        # -------------------------------------------------
        # Subscriber : NodeB confidence
        # ------------------------------------------------
        self.sub_from_node_b = self.create_subscription(
            Detection,
            '/robot8/confidence',
            self.confidence_callback,
            10
        )

        self.get_logger().info('NodeA 대기 중... (/car_detected True 기다리는 중)')
        # --------------------------------------------------
        # Turtlebot Navigator
        # --------------------------------------------------
        self.navigator = TurtleBot4Navigator(namespace='/robot8')

        # -------------------------------------------------
        # Node C service client
        # ------------------------------------------------
        self.node_c_client = self.create_client(SetBool, '/robot8/node_c_enable')


    # =====================================================
    # webcam node 에서 차량 감지 시 호출
    # =====================================================
    def detect_callback(self, msg):
        if not self.node_enabled:
            return
        
        if msg.data and not self.started:
            self.get_logger().info('차량 감지 신호 수신! waypoint patrol 시작')
            self.start_requested = True

    # =====================================================
    # Yolo node 에서 confidence 수신 시 호출
    # =====================================================
    def confidence_callback(self, msg):
        confidence = msg.confidence
        label = msg.label
        
        # if label == 'rc_car' and confidence > 0.7:
        #     self.cancel_requested = True

        if label == 'rc_car':
            if confidence > self.conf_threshold:
                self.confidence_counter = min(10, self.confidence_counter + 1)   
            else:
                self.confidence_counter = max(0, self.confidence_counter - 1)

        # 아직 mission 중이 아니면 무시
        if not self.started:
            return

        # 이미 Node C 요청이 끝났거나 취소가 진행 중이면 중복 방지
        if self.node_c_requested or self.cancel_requested:
            return

        # threshold 이상이면 현재 nav task 취소 요청
        if self.confidence_counter >= self.threshold:
            self.cancel_requested = True
            self.get_logger().info(
                f'confidence 조건 충족: {self.confidence_counter}/{self.threshold} -> 현재 goal 취소 준비'
            )

    # =====================================================
    # Node C SetBool service 호출
    # =====================================================
    def request_node_c_start(self):
        if not self.node_c_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().error('Node C service /robot8/node_c_enable 을 찾을 수 없음')
            return False

        req = SetBool.Request()
        req.data = True

        future = self.node_c_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)

        if not future.done() or future.result() is None:
            self.get_logger().error('Node C service 응답 실패')
            return False

        res = future.result()
        if res.success:
            self.get_logger().info(f'Node C 활성화 성공: {res.message}')
            self.node_c_requested = True
            return True

        self.get_logger().warn(f'Node C 활성화 거절됨: {res.message}')
        return False

    # =====================================================
    # 현재 navigation task 안전하게 취소
    # =====================================================
    def cancel_current_navigation(self):
        self.get_logger().info('실행 중인 navigation goal 취소 요청')
        self.navigator.cancelTask()

        # cancel 완료까지 잠깐 대기
        deadline = time.time() + 3.0
        while rclpy.ok() and time.time() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.navigator.isTaskComplete():
                self.get_logger().info('navigation goal 취소 완료')
                return True

        # timeout 이어도 task 가 끝났는지 한 번 더 확인
        if self.navigator.isTaskComplete():
            self.get_logger().info('navigation goal 취소 완료')
            return True

        self.get_logger().warn('navigation goal 취소 완료를 확인하지 못함')
        return False

    # --------------------------------------------------
    # 메인 patrol 실행
    # --------------------------------------------------
    def execute_mission(self):

        self.started = True
        self.cancel_requested = False

        # mission 종료 후 완전 비활성화

        self.confidence_counter = 0

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

            # 목적지 도착 전까지 대기
            while not self.navigator.isTaskComplete():
                rclpy.spin_once(self, timeout_sec=0.1)

                # confidence 조건을 만족해서 취소 요청이 들어온 경우
                if self.cancel_requested:
                    cancel_ok = self.cancel_current_navigation()
                    self.get_logger().info('Node A patrol 종료, Node C 로 제어 이관')
                    self.started = False
                    self.start_requested = False
                    self.cancel_requested = False
                    if cancel_ok:
                        self.request_node_c_start()
                    else:
                        self.get_logger().warn('goal 취소가 불확실하지만 Node C 요청을 시도함')
                        self.request_node_c_start()
                    return

            self.navigator.info(
                f'[{i+1}/{len(goal_pose)}] 도착 완료! 360도 회전 시작'
            )
            # 도착 후 360도(2*pi) 제자리 회전 명령
            self.navigator.spin(
                spin_dist=2.0 * math.pi
            )

            while not self.navigator.isTaskComplete():
                rclpy.spin_once(self, timeout_sec=0.1)
                if self.cancel_requested:
                    cancel_ok = self.cancel_current_navigation()
                    self.get_logger().info('Node A patrol 종료, Node C 로 제어 이관')
                    self.started = False
                    self.start_requested = False
                    self.cancel_requested = False
                    if cancel_ok:
                        self.request_node_c_start()
                    else:
                        self.get_logger().warn('goal 취소가 불확실하지만 Node C 요청을 시도함')
                        self.request_node_c_start()
                    return

        self.navigator.info('모든 waypoint 순찰 완료')

        self.get_logger().info('미션 종료')
        self.started = False
        self.start_requested = False
        self.cancel_requested = False
        self.confidence_counter = 0

        self.node_enabled = False


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