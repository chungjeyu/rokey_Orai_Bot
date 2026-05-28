#!/usr/bin/env python3

import math
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String

# 🔥 [배터리 중계 추가] BatteryState 메시지 임포트
from sensor_msgs.msg import BatteryState

from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy 

class FollowerNode(Node):
    def __init__(self):
        super().__init__('follower_node')

        self.important_qos = QoSProfile(
           reliability=QoSReliabilityPolicy.RELIABLE,
           durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
           history=QoSHistoryPolicy.KEEP_LAST,
           depth=10
        )

        # 1. 목적지 데이터
        self.targets = {
            "START":      {"prefix": "start", "x": -0.132, "y": 1.019, "yaw": 180.0},
            "GO_TO_HOME": {"prefix": "home",  "x": -1.0223, "y": 1.974, "yaw": 0.0}, # robot3
        }
        
        for cmd, data in self.targets.items():
            prefix = data["prefix"]
            self.declare_parameter(f"{prefix}_x", data["x"])
            self.declare_parameter(f"{prefix}_y", data["y"])
            self.declare_parameter(f"{prefix}_yaw_deg", data["yaw"])

            data["x"] = float(self.get_parameter(f"{prefix}_x").value)
            data["y"] = float(self.get_parameter(f"{prefix}_y").value)
            data["yaw"] = float(self.get_parameter(f"{prefix}_yaw_deg").value)

        # 2. 상태 변수
        self.current_state = None
        self.goal_active = False
        self.current_goal_cmd = None

        # 3. 콜백 그룹 분리
        self.cb_group_cmd = MutuallyExclusiveCallbackGroup()
        self.cb_group_timer = MutuallyExclusiveCallbackGroup()
        self.cb_group_battery = MutuallyExclusiveCallbackGroup() # 🔥 배터리 전용 콜백 그룹

        # 4. 통신 설정
        self.state_pub = self.create_publisher(String, 'follower_state', 10)
        self.result_pub = self.create_publisher(String, 'follower_result', self.important_qos)

        # 🔥 [배터리 중계] GUI로 보낼 원본 타입 퍼블리셔
        # __ns:=/robot3 실행 시 /robot3/battery_status 가 됩니다.
        self.battery_relay_pub = self.create_publisher(BatteryState, 'battery_status', 10)

        # GUI 등에서 오는 직접 명령
        self.create_subscription(
            String, '/leader_cmd', self.cmd_callback, self.important_qos, 
            callback_group=self.cb_group_cmd
        )

        # 🔥 [배터리 중계] 로봇의 실제 배터리 상태 구독
        # __ns:=/robot3 실행 시 /robot3/battery_state 가 됩니다.
        self.create_subscription(
            BatteryState, 'battery_state', self.battery_callback, 10,
            callback_group=self.cb_group_battery
        )

        # 5. Nav2 초기화
        self.navigator = TurtleBot4Navigator()
        self.get_logger().info("✅ Nav2 활성화 완료")

        if not self.navigator.getDockedStatus():
            self.get_logger().info('⚠️ 도킹 해제 상태 감지. 시작 전 도킹을 수행합니다.')
            self.navigator.dock()

        self.create_timer(0.1, self.monitor_nav_status, callback_group=self.cb_group_timer)
        self.set_state("Wait")
        self.get_logger().info("🚀 Follower Node Ready (robot3).")

    # 🔥 [배터리 중계 로직] 데이터를 가공하지 않고 바로 GUI 토픽으로 넘겨줍니다.
    def battery_callback(self, msg):
        self.battery_relay_pub.publish(msg)

    def set_state(self, new_state):
        if self.current_state != new_state:
            self.current_state = new_state
            msg = String()
            msg.data = self.current_state
            self.state_pub.publish(msg)

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()
        if self.goal_active:
            return

        if cmd == "START":
            if self.current_state == "Wait":
                self.set_state("Undock")
                
                if self.navigator.getDockedStatus():
                    self.navigator.undock()
                self.process_movement("START")

        elif cmd == "GO_TO_HOME":
            if self.current_state in ["start_pos", "Tracking"]:
                self.initiate_return_home()

    # 중복되는 홈 복귀 코드를 함수로 분리
    def initiate_return_home(self):
        self.set_state("Go_To_HOME")
        self.get_logger().info("🏠 복귀 시퀀스 시작: GO_TO_HOME으로 이동합니다.")
        
        # Tracking 제어기에게 추종을 강제로 멈추라는 신호 발행
        msg = String()
        msg.data = "STOP_TRACKING"
        self.result_pub.publish(msg)

        self.process_movement("GO_TO_HOME")

    def process_movement(self, cmd):
        target = self.targets[cmd]
        goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(goal_pose)
        self.goal_active = True
        self.current_goal_cmd = cmd
        if cmd != "START":
            self.set_state("goal_planning")

    def monitor_nav_status(self):
        if not self.goal_active:
            return

        if self.navigator.isTaskComplete():
            self.goal_active = False
            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:
                if self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료.")
                    self.set_state("start_pos") 
                    msg = String(); msg.data = "ARRIVED_START"; self.result_pub.publish(msg)

                elif self.current_goal_cmd == "GO_TO_HOME":
                    self.get_logger().info("HOME 도착! Dock 실행")
                    self.set_state("Dock")
                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()
                    self.set_state("Wait")
                    self.current_goal_cmd = None
                    msg = String(); msg.data = "DOCK_COMPLETE"; self.result_pub.publish(msg)

    def create_pose(self, x, y, yaw_deg):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        rad = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(rad/2)
        pose.pose.orientation.w = math.cos(rad/2)
        return pose

def main(args=None):
    rclpy.init(args=args)
    node = FollowerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try: 
        executor.spin()
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()