#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String, Bool  # Bool 타입 추가

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')
        # =========================================================
        # 1. 목적지 데이터 테이블
        # =========================================================
        self.targets = {
            "START":       {"prefix": "start",  "x": -1.266, "y": 0.832,  "yaw": 180.0, "undock_first": True,  "dock_after": False},
            "GO_TO_A":     {"prefix": "area_a", "x": -5.907, "y": 1.106,  "yaw": 0.0,   "undock_first": False, "dock_after": False},
            "GO_TO_B":     {"prefix": "area_b", "x": -3.193, "y": -2.644, "yaw": 0.0,   "undock_first": False, "dock_after": False},
            "RETURN_HOME": {"prefix": "home",   "x": 0.0,    "y": 0.0,    "yaw": 0.0,   "undock_first": False, "dock_after": True}
        }

        # 파라미터 로드
        for cmd, data in self.targets.items():
            prefix = data["prefix"]
            self.declare_parameter(f"{prefix}_x", data["x"])
            self.declare_parameter(f"{prefix}_y", data["y"])
            self.declare_parameter(f"{prefix}_yaw_deg", data["yaw"])

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
        self.is_event_paused = False  # 🔥 이벤트 정지 상태 플래그
        # =========================================================
        # 통신 설정
        # =========================================================
        self.state_pub = self.create_publisher(String, 'leader_state', 10)
        self.result_pub = self.create_publisher(String, 'leader_result', 10)

        self.create_subscription(String, 'leader_cmd', self.cmd_callback, 10)
        self.create_subscription(String, '/follower_state', self.follower_callback, 10)

        self.create_subscription(Bool, 'event_trigger', self.event_callback, 10) # 🔥 이벤트 구독

        # =========================================================
        # Nav2 객체 및 타이머 설정
        # =========================================================
       
        self.navigator = TurtleBot4Navigator()
        self.create_timer(0.5, self.publish_state)
        self.create_timer(0.1, self.monitor_nav_status)

        self.get_logger().info("🚀 이벤트 처리 기능이 포함된 Leader Node 실행 중...")

    # 🔥 이벤트 처리 콜백
    def event_callback(self, msg):
        if msg.data is True:
            if self.goal_active:
                self.get_logger().warn("🚨 이벤트 발생! 작업을 취소하고 정지합니다.")
                self.stop_robot("EVENT_TRIGGERED")
                self.is_event_paused = True
                self.current_state = "EVENT_PAUSED"
        
        elif msg.data is False:
            if self.is_event_paused and self.last_movement_command:
                self.get_logger().info(f"✅ 이벤트 종료! 이전 경로({self.last_movement_command})로 복귀합니다.")
                self.is_event_paused = False
                self.process_movement(self.last_movement_command)

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if cmd in self.targets:
            self.is_event_paused = False # 새 명령 시 플래그 초기화
            self.process_movement(cmd)
            
        elif cmd == "STOP":
            self.stop_robot("GUI_STOP")
            self.is_event_paused = False

    def process_movement(self, cmd):
        """목표지로 이동하는 모든 로직의 단일 창구"""
        if self.goal_active:
            self.get_logger().info(f"이미 {self.current_goal_cmd} 수행 중입니다.")
            return

        target = self.targets[cmd]
        self.last_movement_command = cmd
        
        if target["undock_first"] and self.navigator.getDockedStatus():
           self.get_logger().info("도킹 상태 감지. 언도킹을 시작합니다.")
           self.navigator.undock()

        goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd
        self.current_state = "MOVING"
        self.get_logger().info(f"목적지 [{cmd}] (으)로 이동 시작!")

    def follower_callback(self, msg):
        if msg.data == "STOPPED":
            self.stop_robot("FOLLOWER_STOPPED")

    def monitor_nav_status(self):

        if not self.goal_active: return

        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()
            self.get_logger().info(f"Nav2 작업 완료. 결과: {result}")
            
            if result == TaskResult.SUCCEEDED:
                self.current_state = "WAITING"
                if self.targets[self.current_goal_cmd]["dock_after"]:
                    self.navigator.dock()
            elif result == TaskResult.CANCELED:
                if not self.is_event_paused:
                    self.current_state = "STOPPED"

    def stop_robot(self, reason):
        self.get_logger().info(f"정지 사유: {reason}")
        self.navigator.cancelTask() # 🔥 현재 Nav2 태스크 취소
        self.goal_active = False

    def create_pose(self, x, y, yaw_deg):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        rad = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(rad/2); pose.pose.orientation.w = math.cos(rad/2)
        return pose

    def publish_state(self):
        msg = String(); msg.data = self.current_state
        self.state_pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally: node.destroy_node(); rclpy.shutdown()

if __name__ == "__main__":
    main()