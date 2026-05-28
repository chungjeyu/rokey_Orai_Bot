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

        # =========================
        # Pub/Sub
        # =========================
        self.state_pub = self.create_publisher(String, '/leader_state', 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.create_subscription(String, '/leader_cmd', self.cmd_callback, 10)

        # =========================
        # Nav2
        # =========================
        self.action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # 🔥 Dock Navigator
        self.navigator = TurtleBot4Navigator()

        self.create_timer(0.5, self.publish_state)

    # =========================================================
    # cmd_vel 이동 함수
    # =========================================================
    def move_forward(self, duration=2.0):
        twist = Twist()
        twist.linear.x = 0.2

        start = self.get_clock().now()
        while (self.get_clock().now() - start).nanoseconds / 1e9 < duration:
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.cmd_pub.publish(Twist())

    def turn_right(self, duration=2.0):
        twist = Twist()
        twist.angular.z = -0.5

        start = self.get_clock().now()
        while (self.get_clock().now() - start).nanoseconds / 1e9 < duration:
            self.cmd_pub.publish(twist)
            rclpy.spin_once(self, timeout_sec=0.05)

        self.cmd_pub.publish(Twist())

    # =========================================================
    # 상태 publish
    # =========================================================
    def publish_state(self):
        msg = String()
        msg.data = self.current_state
        self.state_pub.publish(msg)

    # =========================================================
    # 명령 처리
    # =========================================================
    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if self.current_state == "WAITING_FOR_START":
            if cmd == "START":
                self.last_movement_command = "START"

                self.get_logger().info("START → 직진 → 회전 → Nav2")

                self.move_forward()
                self.turn_right()

                self.start_named_goal("START_POINT",
                                      self.start_x,
                                      self.start_y,
                                      self.start_yaw_deg)
            return

        if cmd == "RETURN_HOME":
            self.start_named_goal("HOME",
                                 self.home_x,
                                 self.home_y,
                                 self.home_yaw_deg)

    # =========================================================
    # Nav2 Goal
    # =========================================================
    def start_named_goal(self, name, x, y, yaw):
        self.send_goal(x, y, yaw, name)

    def send_goal(self, x, y, yaw, name):
        self.action_client.wait_for_server()

        goal = NavigateToPose.Goal()
        goal.pose = PoseStamped()
        goal.pose.header.frame_id = 'map'

        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y

        z = math.sin(math.radians(yaw)/2)
        w = math.cos(math.radians(yaw)/2)

        goal.pose.pose.orientation.z = z
        goal.pose.pose.orientation.w = w

        self.current_goal_name = name

        future = self.action_client.send_goal_async(goal)
        future.add_done_callback(self.goal_response)

    def goal_response(self, future):
        handle = future.result()
        result_future = handle.get_result_async()
        result_future.add_done_callback(self.goal_result)

    def goal_result(self, future):
        self.get_logger().info(f"{self.current_goal_name} 도착")

        # 🔥 HOME 도착 시 Dock 실행
        if self.current_goal_name == "HOME":
            self.get_logger().info("도킹 시작")

            if not self.navigator.getDockedStatus():
                self.navigator.dock()