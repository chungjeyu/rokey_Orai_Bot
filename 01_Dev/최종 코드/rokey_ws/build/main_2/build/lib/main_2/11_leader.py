#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String, Bool

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult, TurtleBot4Directions

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')
        # =========================================================
        # 1. 목적지 데이터 테이블 (Flow Chart 매칭)
        # =========================================================
        self.targets = {
            "START":      {"prefix": "start",  "x": -1.266, "y": 0.832,  "yaw": 180.0},
            "GO_TO_A":    {"prefix": "area_a", "x": -5.907, "y": 1.106,  "yaw": 0.0},
            "GO_TO_B":    {"prefix": "area_b", "x": -3.193, "y": -2.644, "yaw": 0.0},
            "GO_TO_HOME": {"prefix": "home",   "x": 0.0,    "y": 0.0,    "yaw": 0.0}
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
        # 상태 변수 (Flow Chart 용어와 1:1 매칭)
        # =========================================================
        self.current_state = "Booting"
        self.goal_active = False
        self.current_goal_cmd = None # 이벤트 종료 후 경로 저장용
        self.is_threatened = False   # 🔥 이벤트 정지 상태 플래그
        # =========================================================
        # 통신 설정
        # =========================================================
        self.state_pub = self.create_publisher(String, 'leader_state', 10)
        self.result_pub = self.create_publisher(String, 'leader_result', 10) 

        self.create_subscription(String, 'leader_cmd', self.cmd_callback, 10)
        self.create_subscription(Bool, 'event_trigger', self.event_callback, 10) 

        # =========================================================
        # Nav2 시스템 초기화 (명령 씹힘 방지용 대기만 유지)
        # =========================================================
        self.navigator = TurtleBot4Navigator()
        
        self.get_logger().info("⏳ Nav2 시스템이 완전히 활성화될 때까지 대기 중...")
        self.navigator.waitUntilNav2Active() 
        self.get_logger().info("✅ Nav2 시스템 활성화 완료!")

        # 시작 전 물리적 도킹 상태 보장 (플로우차트 정상 시작을 위함)
        if not self.navigator.getDockedStatus():
            self.get_logger().info('⚠️ 도킹 해제 상태 감지. 시작 전 도킹을 수행합니다.')
            self.navigator.dock()

        self.create_timer(0.5, self.publish_state)
        self.create_timer(0.1, self.monitor_nav_status)
                # Initial Pose
        initial_pose = self.navigator.getPoseStamped(
            [0.0, 0.0],                         # 리더 초기 좌표
            TurtleBot4Directions.NORTH
        )
        self.navigator.setInitialPose(initial_pose)

        self.current_state = "Wait"
        self.get_logger().info("🚀 로봇 초기화 완료! Flow Chart [Wait] 상태 진입.")

    # =========================================================
    # [Flow Chart]: threat state? -> stay_robot / 다시 원래 목표로 복귀
    # =========================================================
    def event_callback(self, msg):
        if msg.data is True: 
            if self.goal_active and not self.is_threatened:
                self.get_logger().warn("🚨 threat state: Y -> stay_robot")
                self.navigator.cancelTask()
                self.is_threatened = True
                self.current_state = "stay_robot"
        
        elif msg.data is False: 
            if self.is_threatened and self.current_goal_cmd:
                self.get_logger().info("✅ threat state: N -> 다시 goal_planning")
                self.is_threatened = False
                self.process_movement(self.current_goal_cmd) 

    # =========================================================
    # [Flow Chart]: Wait -> Detect? -> Undock -> start_pos / goal_A? / goal_B?
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if cmd == "START" and self.current_state == "Wait":
            self.current_state = "Undock"
            if self.navigator.getDockedStatus():
                self.navigator.undock()
            self.process_movement("START") 

        elif cmd == "GO_TO_A": 
            self.current_state = "Go_To_A"
            self.process_movement("GO_TO_A")
            
        elif cmd == "GO_TO_B": 
            self.current_state = "Go_To_B"
            self.process_movement("GO_TO_B")

    def process_movement(self, cmd):
        target = self.targets[cmd]
        goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd
        
        if cmd not in ["START", "GO_TO_HOME"]:
            self.current_state = "goal_planning" 

    # =========================================================
    # [Flow Chart]: isTaskComplete(goal?) -> 보고 -> Go_To_HOME -> Dock -> Wait
    # =========================================================
    def monitor_nav_status(self):
        if not self.goal_active: return

        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()
            
            if result == TaskResult.SUCCEEDED:
                # 1. 목적지(A or B) 도착 시
                if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                    self.get_logger().info(f"목적지 도착! 관제소 보고: {self.current_goal_cmd}")
                    report_msg = String()
                    report_msg.data = f"ARRIVED_{self.current_goal_cmd}"
                    self.result_pub.publish(report_msg)

                    self.get_logger().info("자동 Go_To_HOME 실행")
                    self.current_state = "Go_To_HOME"
                    self.process_movement("GO_TO_HOME")
                
                # 2. 초기 시작 위치(HOME) 도착 시
                elif self.current_goal_cmd == "GO_TO_HOME":
                    self.get_logger().info("초기 위치(HOME) 도착! Dock 실행")
                    self.current_state = "Dock"
                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()
                    
                    # 도킹 후 위치 보정 없이 바로 Wait 상태로 전환
                    self.current_state = "Wait"
                    self.current_goal_cmd = None

                # 3. start_pos 도착 시
                elif self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료. 목적지 명령 대기")
                    self.current_state = "start_pos"

            elif result == TaskResult.CANCELED:
                if self.is_threatened:
                    pass # stay_robot 상태 유지

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

    def publish_state(self):
        msg = String()
        msg.data = self.current_state
        self.state_pub.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    try: 
        rclpy.spin(node)
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()