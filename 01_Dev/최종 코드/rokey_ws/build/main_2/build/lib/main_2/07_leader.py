#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

# TurtleBot4Navigator 모듈
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')

        # =========================================================
        # 🎯 1. 단일 데이터 테이블 (중복 완전 제거의 핵심)
        # 파라미터 접두사, 좌표, 방향, 도킹/언도킹 속성을 한곳에서 관리
        # =========================================================
        self.targets = {
            "START":       {"prefix": "start",  "x": -1.266, "y": 0.832,  "yaw": 180.0, "undock_first": True,  "dock_after": False},
            "GO_TO_A":     {"prefix": "area_a", "x": -5.907, "y": 1.106,  "yaw": 0.0,   "undock_first": False, "dock_after": False},
            "GO_TO_B":     {"prefix": "area_b", "x": -3.193, "y": -2.644, "yaw": 0.0,   "undock_first": False, "dock_after": False},
            "RETURN_HOME": {"prefix": "home",   "x": 0.0,    "y": 0.0,    "yaw": 0.0,   "undock_first": False, "dock_after": True}
        }

        # 반복문 단 5줄로 ROS2 파라미터 선언 및 최신값 로드 완료
        for cmd, data in self.targets.items():
            prefix = data["prefix"]
            self.declare_parameter(f"{prefix}_x", data["x"])
            self.declare_parameter(f"{prefix}_y", data["y"])
            self.declare_parameter(f"{prefix}_yaw_deg", data["yaw"])

            # 사용자가 파라미터를 변경해서 실행했을 경우를 대비해 값 업데이트
            data["x"] = float(self.get_parameter(f"{prefix}_x").value)
            data["y"] = float(self.get_parameter(f"{prefix}_y").value)
            data["yaw"] = float(self.get_parameter(f"{prefix}_yaw_deg").value)

        # =========================================================
        # 상태 변수
        # =========================================================
        self.current_state = "WAITING_FOR_START"
        self.goal_active = False
        self.current_goal_cmd = None
        self.last_movement_command = None

        # =========================================================
        # 통신 설정 (Pub/Sub)
        # =========================================================
        self.state_pub = self.create_publisher(String, '/leader_state', 10)
        self.result_pub = self.create_publisher(String, '/leader_result', 10)

        self.create_subscription(String, '/leader_cmd', self.cmd_callback, 10)
        self.create_subscription(String, '/follower_state', self.follower_callback, 10)

        # =========================================================
        # Nav2 객체 및 타이머 설정
        # =========================================================
        self.navigator = TurtleBot4Navigator()

        self.create_timer(0.5, self.publish_state)
        self.create_timer(0.1, self.monitor_nav_status)  # 논블로킹 상태 확인
        
        # 🔥 여기에 시작 알림 로그 추가!
        self.get_logger().info("==================================================")
        self.get_logger().info("🚀 Leader Node 가 성공적으로 실행되었습니다!")
        self.get_logger().info("현재 상태: WAITING_FOR_START (명령 대기 중)")
        self.get_logger().info("명령어 예시: START, GO_TO_A, RETURN_HOME, STOP")
        self.get_logger().info("==================================================")

    # =========================================================
    # 유틸리티 (메시지 발행 통합 등)
    # =========================================================
    def publish_msg(self, publisher, text):
        """String 퍼블리셔 중복 제거"""
        msg = String()
        msg.data = text
        publisher.publish(msg)

    def publish_state(self):
        self.publish_msg(self.state_pub, self.current_state)

    def create_pose(self, x, y, yaw_deg):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        yaw_rad = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(yaw_rad / 2)
        pose.pose.orientation.w = math.cos(yaw_rad / 2)
        return pose

    # =========================================================
    # 🎯 2. 명령어 수신부 (if-elif 지옥 탈출)
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        # [A] 이동 명령인 경우 (targets 딕셔너리에 존재하는 키면 무조건 통과)
        if cmd in self.targets:
            # START 전 대기 상태 확인
            if cmd == "START" and self.current_state != "WAITING_FOR_START":
                return
            self.process_movement(cmd)

        # [B] 그 외 제어 명령
        elif cmd == "STOP":
            self.stop_robot("GUI_STOP")
            
        elif cmd == "RESUME_LAST":
            if self.last_movement_command:
                self.process_movement(self.last_movement_command)

    def process_movement(self, cmd):
        """목표지로 이동하는 모든 로직의 단일 창구"""
        if self.goal_active:
            self.get_logger().info(f"이미 {self.current_goal_cmd} 수행 중입니다.")
            return

        target = self.targets[cmd]
        self.last_movement_command = cmd

        # 출발 전 언도킹이 필요한 목적지인가? (START)
        if target["undock_first"] and self.navigator.getDockedStatus():
            self.get_logger().info("도킹 상태 감지. 언도킹을 시작합니다.")
            self.navigator.undock()

        # 목표 좌표 설정 및 이동 명령 (비동기)
        goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd
        self.current_state = "MOVING"
        self.get_logger().info(f"목적지 [{cmd}] (으)로 이동 시작!")

    def follower_callback(self, msg):
        if msg.data == "STOPPED":
            self.stop_robot("FOLLOWER_STOPPED")

    # =========================================================
    # 🎯 3. 상태 모니터링 (논블로킹 타이머)
    # =========================================================
    def monitor_nav_status(self):
        if not self.goal_active:
            return

        # Nav2 작업 완료 여부 확인
        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:
                self.get_logger().info(f"[{self.current_goal_cmd}] 도착 완료!")
                self.current_state = "WAITING"
                self.publish_msg(self.result_pub, f"ARRIVED_{self.current_goal_cmd}")

                # 도착 후 도킹이 필요한 목적지인가? (RETURN_HOME)
                target = self.targets.get(self.current_goal_cmd)
                if target and target["dock_after"] and not self.navigator.getDockedStatus():
                    self.get_logger().info("도킹 시퀀스 시작")
                    self.navigator.dock()

            elif result == TaskResult.CANCELED:
                self.get_logger().info("이동 취소됨.")
                self.current_state = "STOPPED"
                
            elif result == TaskResult.FAILED:
                self.get_logger().error("이동 실패! 경로를 찾을 수 없거나 막혔습니다.")
                self.current_state = "FAILED"
                self.publish_msg(self.result_pub, "NAV_FAILED")

    # =========================================================
    # 정지
    # =========================================================
    def stop_robot(self, reason):
        self.get_logger().info(f"정지 명령: {reason}")
        if self.goal_active:
            self.navigator.cancelTask()
        self.goal_active = False
        self.current_state = "STOPPED"


def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    
    try:
        # 노드를 실행 상태로 유지
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("사용자에 의해 종료됩니다 (Ctrl+C)")
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == "__main__":
    main()