#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import Twist, PoseStamped
from std_msgs.msg import String

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')

        # =========================
        # 파라미터
        # =========================
        self.declare_parameter('home_x', 0.0)
        self.declare_parameter('home_y', 0.0)
        self.declare_parameter('home_yaw_deg', 0.0)

        self.declare_parameter('start_x', -1.266)
        self.declare_parameter('start_y', 0.832)
        self.declare_parameter('start_yaw_deg', 180.0)

        self.declare_parameter('area_a_x', -5.907)
        self.declare_parameter('area_a_y', 1.106)
        self.declare_parameter('area_a_yaw_deg', 0.0)

        self.declare_parameter('area_b_x', -3.193)
        self.declare_parameter('area_b_y', -2.644)
        self.declare_parameter('area_b_yaw_deg', 0.0)

        self.home_x = float(self.get_parameter('home_x').value)
        self.home_y = float(self.get_parameter('home_y').value)
        self.home_yaw_deg = float(self.get_parameter('home_yaw_deg').value)

        self.start_x = float(self.get_parameter('start_x').value)
        self.start_y = float(self.get_parameter('start_y').value)
        self.start_yaw_deg = float(self.get_parameter('start_yaw_deg').value)

        self.area_a_x = float(self.get_parameter('area_a_x').value)
        self.area_a_y = float(self.get_parameter('area_a_y').value)
        self.area_a_yaw_deg = float(self.get_parameter('area_a_yaw_deg').value)

        self.area_b_x = float(self.get_parameter('area_b_x').value)
        self.area_b_y = float(self.get_parameter('area_b_y').value)
        self.area_b_yaw_deg = float(self.get_parameter('area_b_yaw_deg').value)

        # =========================
        # 상태
        # =========================
        self.current_state = "WAITING_FOR_START"
        self.goal_active = False
        self.goal_handle = None
        self.current_goal_name = None
        self.last_movement_command = None
        self.follower_state = "UNKNOWN"

        # =========================
        # Pub/Sub
        # =========================
        self.state_pub = self.create_publisher(String, '/leader_state', 10)
        self.result_pub = self.create_publisher(String, '/leader_result', 10)

        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.create_subscription(String, '/leader_cmd', self.cmd_callback, 10)
        self.create_subscription(String, '/follower_state', self.follower_callback, 10)

        # =========================
        # Nav2
        # =========================
        self.action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.navigator = TurtleBot4Navigator()

        self.create_timer(0.5, self.publish_state)

    # =========================================================
    # 🔥 추가된 cmd_vel 제어 함수
    # =========================================================
    def move_forward(self, duration=2.0, speed=0.2):
        twist = Twist()
        twist.linear.x = speed

        start_time = self.get_clock().now()

        while (self.get_clock().now() - start_time).nanoseconds / 1e9 < duration:
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.stop_cmd_vel()

    def turn_right(self, duration=2.0, angular_speed=-0.5):
        twist = Twist()
        twist.angular.z = angular_speed

        start_time = self.get_clock().now()

        while (self.get_clock().now() - start_time).nanoseconds / 1e9 < duration:
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.stop_cmd_vel()

    # =========================================================
    # 유틸
    # =========================================================
    def yaw_deg_to_quaternion_zw(self, yaw_deg):
        yaw_rad = math.radians(yaw_deg)
        return math.sin(yaw_rad/2), math.cos(yaw_rad/2)

    def publish_state(self):
        msg = String()
        msg.data = self.current_state
        self.state_pub.publish(msg)

    def publish_result(self, text):
        msg = String()
        msg.data = text
        self.result_pub.publish(msg)

    def stop_cmd_vel(self):
        self.cmd_pub.publish(Twist())

    # =========================================================
    # 🔥 START 수정된 핵심 부분
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if self.current_state == "WAITING_FOR_START":
            if cmd == "START":
                self.last_movement_command = "START"

                self.get_logger().info("START → 직진 → 우회전 → Nav2 이동")

                # 🔥 여기 핵심 추가
                self.move_forward(duration=2.0)
                self.turn_right(duration=2.0)

                # Nav2 이동
                self.start_named_goal(
                    "START_POINT",
                    self.start_x,
                    self.start_y,
                    self.start_yaw_deg
                )
            return

        if cmd == "GO_TO_A":
            self.last_movement_command = "GO_TO_A"
            self.start_named_goal("AREA_A", self.area_a_x, self.area_a_y, self.area_a_yaw_deg)

        elif cmd == "GO_TO_B":
            self.last_movement_command = "GO_TO_B"
            self.start_named_goal("AREA_B", self.area_b_x, self.area_b_y, self.area_b_yaw_deg)

        elif cmd == "RETURN_HOME":
            self.last_movement_command = "RETURN_HOME"
            self.start_named_goal("HOME", self.home_x, self.home_y, self.home_yaw_deg)

        elif cmd == "STOP":
            self.stop_robot("GUI_STOP")

        elif cmd == "RESUME_LAST":
            self.resume_last_goal()

    def follower_callback(self, msg):
        if msg.data == "STOPPED":
            self.stop_robot("FOLLOWER_STOPPED")

    # =========================================================
    # Nav2
    # =========================================================
    def start_named_goal(self, name, x, y, yaw):
        if self.goal_active:
            return

        self.send_goal(x, y, yaw, name)

    def send_goal(self, x, y, yaw, name):
        self.action_client.wait_for_server()

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'

        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y

        z, w = self.yaw_deg_to_quaternion_zw(yaw)
        goal.pose.pose.orientation.z = z
        goal.pose.pose.orientation.w = w

        self.goal_active = True
        self.current_goal_name = name
        self.current_state = "MOVING"

        future = self.action_client.send_goal_async(goal)
        future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        handle = future.result()

        if not handle.accepted:
            self.goal_active = False
            return

        self.goal_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        self.goal_active = False
        self.current_state = "WAITING"
            # 🔥 HOME 도착 시 docking만 추가
        if self.current_goal_name == "HOME":
            self.get_logger().info("도킹 시작")

            if not self.navigator.getDockedStatus():
                self.navigator.dock()

    # =========================================================
    # STOP / RESUME
    # =========================================================
    def stop_robot(self, reason):
        if self.goal_handle:
            self.goal_handle.cancel_goal_async()

        self.stop_cmd_vel()
        self.current_state = "STOPPED"

    def resume_last_goal(self):
        if self.last_movement_command == "START":
            self.start_named_goal("START_POINT", self.start_x, self.start_y, self.start_yaw_deg)


def main():
    rclpy.init()
    node = LeaderNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()