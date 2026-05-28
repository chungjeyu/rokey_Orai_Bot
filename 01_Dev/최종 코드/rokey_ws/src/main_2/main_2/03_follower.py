#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class FollowerNode(Node):
    def __init__(self):
        super().__init__('follower_node')

        # =========================================================
        # 1. 목적지 데이터 
        # =========================================================
        self.targets = {
            "START":      {"prefix": "start", "x": -0.132, "y": 1.019, "yaw": 180.0},
            # "GO_TO_HOME": {"prefix": "home",  "x": 0.0,    "y": 2.017, "yaw": 0.0} # robot4 
            "GO_TO_HOME": {"prefix": "home",  "x": -2.2824,    "y": -1.089, "yaw": 0.0} # robot3
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
        # 2. 상태 변수 
        # =========================================================
        self.current_state = "Booting"
        self.goal_active = False
        self.current_goal_cmd = None

        # =========================================================
        # 3. 통신 설정
        # =========================================================
        self.state_pub = self.create_publisher(String, 'follower_state', 10)
        self.result_pub = self.create_publisher(String, 'follower_result', 10)

        self.create_subscription(String, 'follower_cmd', self.cmd_callback, 10)

        # =========================================================
        # 4. Nav2 초기화
        # =========================================================
        self.navigator = TurtleBot4Navigator()

        self.get_logger().info("⏳ Nav2 활성화 대기 중...")
        # self.navigator.waitUntilNav2Active()
        self.get_logger().info("✅ Nav2 활성화 완료")

        # 초기 도킹 상태 보장
        if not self.navigator.getDockedStatus():
            self.get_logger().info('⚠️ 도킹 해제 상태 감지. 시작 전 도킹을 수행합니다.')
            self.navigator.dock()

        self.create_timer(0.5, self.publish_state)
        self.create_timer(0.1, self.monitor_nav_status)

        self.current_state = "Wait"
        self.get_logger().info("🚀 Follower Flow Chart [Wait] 상태 진입.")

    # =========================================================
    # 명령 처리: Wait -> Undock -> start_pos -> (Tracking) -> Go_To_HOME -> Dock
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if self.goal_active:
            return

        # 1. 시작 명령 (GUI -> Follower)
        if cmd == "START":
            if self.current_state == "Wait":
                self.current_state = "Undock"
                if self.navigator.getDockedStatus():
                    self.navigator.undock()
                self.process_movement("START")
            else:
                self.get_logger().debug("현재 Wait 상태가 아니므로 START 명령을 무시합니다.")

        # 2. 복귀 명령 (Leader 임무 종료 후 GUI -> Follower)
        elif cmd == "GO_TO_HOME":
            # ⚓ [수정 포인트] start_pos 대기 중이거나, 중장비 추종(Tracking) 중일 때 모두 수락
            if self.current_state in ["start_pos", "Tracking"]:
                self.current_state = "Go_To_HOME"
                
                # 🛑 [추후 추가할 부분] 여기서 YOLO/Depth 추종 노드를 중지하는 명령을 넣으시면 됩니다.
                # ex) self.stop_tracking_routine()
                self.get_logger().info("복귀 명령 수신. 추종을 중지하고 HOME으로 복귀합니다.")

                self.process_movement("GO_TO_HOME")
            else:
                self.get_logger().debug(f"현재 '{self.current_state}' 상태이므로 GO_TO_HOME 명령을 무시합니다.")

    # =========================================================
    # 이동 처리
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
    # 상태 감시 및 완료 처리
    # =========================================================
    def monitor_nav_status(self):
        if not self.goal_active:
            return

        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:

                # 1. START 도착 -> 추종 시작 대기
                if self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료. 추종 대기/시작")
                    self.current_state = "start_pos" 
                    
                    # 🚀 [추후 추가할 부분] 여기서 바로 Tracking 상태로 넘어가게 할 수도 있습니다.
                    # self.current_state = "Tracking"
                    
                    msg = String()
                    msg.data = "ARRIVED_START"
                    self.result_pub.publish(msg)

                # 2. 초기 위치(HOME) 도착 -> 도킹
                elif self.current_goal_cmd == "GO_TO_HOME":
                    self.get_logger().info("초기 위치(HOME) 도착! Dock 실행")
                    self.current_state = "Dock"
                    
                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()

                    # 도킹 완료 후 사이클 초기화
                    self.current_state = "Wait"
                    self.current_goal_cmd = None

                    msg = String()
                    msg.data = "DOCK_COMPLETE"
                    self.result_pub.publish(msg)

            elif result == TaskResult.CANCELED:
                pass 

    # =========================================================
    # Pose 생성
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


def main(args=None):
    rclpy.init(args=args)
    node = FollowerNode()
    try: 
        rclpy.spin(node)
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()