#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor # 🔥 추가: 멀티스레드 실행기
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup # 🔥 추가: 콜백 그룹
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from std_msgs.msg import String

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')
        
        # =========================================================
        # 🔥 콜백 그룹(Callback Group) 설정 🔥
        # 각기 다른 그룹에 할당된 콜백들은 멀티스레드 환경에서 병렬로 실행됩니다.
        # =========================================================
        self.cmd_cb_group = MutuallyExclusiveCallbackGroup()   # 관제소 명령 수신용
        self.pose_cb_group = MutuallyExclusiveCallbackGroup()  # 실시간 위치 수신용
        self.timer_cb_group = MutuallyExclusiveCallbackGroup() # Nav2 상태 모니터링 타이머용

        # =========================================================
        # 1. 목적지 데이터 테이블
        # =========================================================
        self.targets = {
            "START":      {"prefix": "start",  "x": -1.266, "y": 0.832,  "yaw": 180.0},
            "GO_TO_A":    {"prefix": "area_a", "x": -5.907, "y": 1.106,  "yaw": 0.0},
            "GO_TO_B":    {"prefix": "area_b", "x": -3.193, "y": -2.644, "yaw": 0.0},
            "GO_TO_HOME": {"prefix": "home",   "x": -0.103, "y": 0.0741,    "yaw": 0.0}
        }

        for cmd, data in self.targets.items():
            prefix = data["prefix"]
            self.declare_parameter(f"{prefix}_x", data["x"])
            self.declare_parameter(f"{prefix}_y", data["y"])
            self.declare_parameter(f"{prefix}_yaw_deg", data["yaw"])

            data["x"] = float(self.get_parameter(f"{prefix}_x").value)
            data["y"] = float(self.get_parameter(f"{prefix}_y").value)
            data["yaw"] = float(self.get_parameter(f"{prefix}_yaw_deg").value)

        # Follower 관련 파라미터 및 변수
        self.declare_parameter("max_follower_dist", 2.0)
        self.declare_parameter("resume_follower_dist", 1.5)
        self.max_f_dist = self.get_parameter("max_follower_dist").value
        self.resume_f_dist = self.get_parameter("resume_follower_dist").value
        
        self.leader_pose = None
        self.follower_pose = None
        self.is_waiting_for_follower = False 
        self.current_goal_pose = None        

        # 상태 변수
        self.current_state = None  
        self.goal_active = False
        self.current_goal_cmd = None 
        self.is_threatened = False   
        
        # =========================================================
        # 통신 설정 (콜백 그룹 지정)
        # =========================================================
        self.state_pub = self.create_publisher(String, 'leader_state', 10)
        self.result_pub = self.create_publisher(String, 'leader_result', 10) 

        # 🔥 명령어 수신 구독자에 cmd_cb_group 할당
        self.create_subscription(
            String, 'leader_cmd', self.cmd_callback, 10, 
            callback_group=self.cmd_cb_group)

        # 🔥 위치 수신 구독자에 pose_cb_group 할당 (위치 업데이트가 다른 로직을 막지 않음)
        self.create_subscription(
            PoseWithCovarianceStamped, 'amcl_pose', self.leader_pose_callback, 10, 
            callback_group=self.pose_cb_group)
        self.create_subscription(
            PoseWithCovarianceStamped, '/robot3/amcl_pose', self.follower_pose_callback, 10, 
            callback_group=self.pose_cb_group)

        # =========================================================
        # Nav2 시스템 초기화 및 타이머
        # =========================================================
        self.navigator = TurtleBot4Navigator()
        
        self.get_logger().info("⏳ Nav2 시스템 활성화 대기 중...")
        self.get_logger().info("✅ Nav2 시스템 활성화 완료!")

        if not self.navigator.getDockedStatus():
            self.get_logger().info('⚠️ 도킹 해제 상태 감지. 시작 전 도킹을 수행합니다.')
            self.navigator.dock()

        # 🔥 타이머에 timer_cb_group 할당
        self.create_timer(0.1, self.monitor_nav_status, callback_group=self.timer_cb_group)
        
        self.set_state("Wait")
        self.get_logger().info("🚀 Flow Chart [Wait] 상태 진입.")

    def leader_pose_callback(self, msg):
        self.leader_pose = msg.pose.pose.position

    def follower_pose_callback(self, msg):
        self.follower_pose = msg.pose.pose.position

    def get_follower_distance(self):
        if self.leader_pose is None or self.follower_pose is None:
            return -1.0 
        dx = self.leader_pose.x - self.follower_pose.x
        dy = self.leader_pose.y - self.follower_pose.y
        return math.sqrt(dx**2 + dy**2)

    def set_state(self, new_state):
        if self.current_state != new_state:
            self.current_state = new_state
            msg = String()
            msg.data = self.current_state
            self.state_pub.publish(msg)

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if self.is_threatened or self.goal_active:
            return 

        if cmd == "START":
            if self.current_state == "Wait":
                self.set_state("Undock")
                if self.navigator.getDockedStatus():
                    self.navigator.undock()
                self.process_movement("START")

        elif cmd in ["GO_TO_A", "GO_TO_B"]:
            if self.current_state == "start_pos":
                self.set_state(f"Go_To_{cmd[-1]}") 
                self.process_movement(cmd)

    def process_movement(self, cmd):
        target = self.targets[cmd]
        
        self.current_goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(self.current_goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd
        self.is_waiting_for_follower = False
        
        if cmd not in ["START", "GO_TO_HOME"]:
            self.set_state("goal_planning") 

    def monitor_nav_status(self):
        if not self.goal_active: return

        # Follower 거리 체크 및 정지/재출발 로직
        dist = self.get_follower_distance()
        if dist >= 0:
            if dist > self.max_f_dist and not self.is_waiting_for_follower:
                self.get_logger().warn(f"🛑 Follower 거리 멀어짐 ({dist:.2f}m). 정지 및 대기합니다.")
                self.navigator.cancelTask() 
                self.is_waiting_for_follower = True
                self.set_state("Wait_Follower") 
                return 

            elif dist <= self.resume_f_dist and self.is_waiting_for_follower:
                self.get_logger().info(f"▶️ Follower 접근 확인 ({dist:.2f}m). 재출발합니다.")
                self.navigator.goToPose(self.current_goal_pose) 
                self.is_waiting_for_follower = False
                
                if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                    self.set_state("goal_planning")
                elif self.current_goal_cmd == "START":
                    self.set_state("Go_To_START")
                return

        if self.is_waiting_for_follower:
            return

        if self.navigator.isTaskComplete():
            result = self.navigator.getResult()
            
            if result == TaskResult.SUCCEEDED:
                self.goal_active = False 
                if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                    self.get_logger().info(f"목적지 도착! 관제소 보고: {self.current_goal_cmd}")
                    report_msg = String()
                    report_msg.data = f"ARRIVED_{self.current_goal_cmd}"
                    self.result_pub.publish(report_msg)

                    self.get_logger().info("자동 Go_To_HOME 실행")
                    self.set_state("Go_To_HOME")
                    self.process_movement("GO_TO_HOME")
                
                elif self.current_goal_cmd == "GO_TO_HOME":
                    self.get_logger().info("초기 위치(HOME) 도착! Dock 실행")
                    self.set_state("Dock")
                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()
                    
                    self.set_state("Wait")
                    self.current_goal_cmd = None

                elif self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료. 목적지 명령 대기")
                    self.set_state("start_pos")
                    report_msg = String()
                    report_msg.data = f"ARRIVED_{self.current_goal_cmd}"
                    self.result_pub.publish(report_msg)

            elif result == TaskResult.CANCELED:
                if self.is_waiting_for_follower:
                    pass 
                elif self.is_threatened:
                    self.goal_active = False
                else:
                    self.goal_active = False

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

def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    
    # =========================================================
    # 🔥 MultiThreadedExecutor 적용 부분 🔥
    # 스레드 개수(num_threads)를 지정하지 않으면 시스템 CPU 코어 수에 맞춰 자동 생성됩니다.
    # =========================================================
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    
    try: 
        executor.spin() # rclpy.spin(node) 대신 executor.spin() 사용
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()