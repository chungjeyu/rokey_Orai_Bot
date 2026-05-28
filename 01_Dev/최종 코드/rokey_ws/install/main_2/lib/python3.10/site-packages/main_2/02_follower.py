#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult
# 아키텍쳐 흐름 : wait -> Detect? -> Undock -> start_pos -> Goal? -> GO_TO_HOME -> DOCK 
#                                                               - 이 사이에 GUI에서 A arrived 명령받으면
# 내 코드에서는?
# Detect 부분은 X  -> 나중에 팀원과 합칠 에정
# wait -> start_pose
# 임의 Goal 좌표 -> GO_TO_HOME + Docking 까지 구현

# Detect는 "YOLO + Depth로 탐지할 것이며 따라가는 것까지" 
class FollowerNode(Node):
    def __init__(self):
        super().__init__('follower_node')

        # =========================================================
        # 1. 목적지 데이터 (leader 스타일)
        # =========================================================
        self.targets = {
            "START": {"prefix": "start", "x": -0.132, "y": 1.019, "yaw": 180.0},
            "DOCK":  {"prefix": "dock",  "x": 0.0,    "y": 2.017, "yaw": 0.0}
        }

        # =========================================================
        # 상태 변수 (완전 통일)
        # =========================================================
        self.current_state = "Booting"
        self.goal_active = False
        self.current_goal_cmd = None

        # =========================================================
        # 통신 (패턴 통일)
        # =========================================================
        self.state_pub = self.create_publisher(String, 'follower_state', 10)
        self.result_pub = self.create_publisher(String, 'follower_result', 10)

        self.create_subscription(String, 'follower_cmd', self.cmd_callback, 10)

        # =========================================================
        # Nav2 초기화 (leader와 동일)
        # =========================================================
        self.navigator = TurtleBot4Navigator()

        self.get_logger().info("⏳ Nav2 활성화 대기 중...")
        self.navigator.waitUntilNav2Active()
        self.get_logger().info("✅ Nav2 활성화 완료")

        # 초기 도킹 상태 보장
        if not self.navigator.getDockedStatus():
            self.navigator.dock()

        self.create_timer(0.5, self.publish_state)
        self.create_timer(0.1, self.monitor_nav_status)

        self.current_state = "Wait"

    # =========================================================
    # 명령 처리 (leader 스타일)
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if cmd == "START" and self.current_state == "Wait":
            self.current_state = "Undock"

            if self.navigator.getDockedStatus():
                self.navigator.undock()

            self.process_movement("START")

        elif cmd == "DOCK":
            if self.current_state == "Dock":
                return

            self.current_state = "Go_To_Dock"
            self.process_movement("DOCK")

    # =========================================================
    # 이동 처리 (완전 동일)
    # =========================================================
    def process_movement(self, cmd):
        target = self.targets[cmd]

        goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd

        if cmd != "START":
            self.current_state = "goal_planning"

    # =========================================================
    # 상태 감시 (leader 구조 동일)
    # =========================================================
    def monitor_nav_status(self):
        if not self.goal_active:
            return

        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:

                # START 도착
                if self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료")

                    msg = String()
                    msg.data = "START_ARRIVED"
                    self.result_pub.publish(msg)

                    self.current_state = "start_pos"

                # DOCK 이동 완료
                elif self.current_goal_cmd == "DOCK":
                    self.get_logger().info("도킹 위치 도착")

                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()

                    self.current_state = "Dock"

                    msg = String()
                    msg.data = "DOCK_COMPLETE"
                    self.result_pub.publish(msg)

            elif result == TaskResult.CANCELED:
                pass

    # =========================================================
    # Pose 생성 (동일)
    # =========================================================
    def create_pose(self, x, y, yaw_deg):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()

        pose.pose.position.x = x
        pose.pose.position.y = y

        rad = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(rad/2)
        pose.pose.orientation.w = math.cos(rad/2)

        return pose

    # =========================================================
    # 상태 publish
    # =========================================================
    def publish_state(self):
        msg = String()
        msg.data = self.current_state
        self.state_pub.publish(msg)