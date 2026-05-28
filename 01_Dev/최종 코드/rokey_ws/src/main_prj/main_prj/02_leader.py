#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from nav2_msgs.action import NavigateToPose
from geometry_msgs.msg import Twist, PoseStamped
from std_msgs.msg import String


class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')

        # =========================================================
        # 파라미터
        # =========================================================
        # 초기 복귀 위치 (도킹 근처 좌표)
        self.declare_parameter('home_x', 0.0)
        self.declare_parameter('home_y', 0.0)
        self.declare_parameter('home_yaw_deg', 0.0)

        # 시작 버튼을 눌렀을 때 가야 하는 시작 지점
        self.declare_parameter('start_x', 1.0)
        self.declare_parameter('start_y', 0.0)
        self.declare_parameter('start_yaw_deg', 0.0)

        # 작업 구역 A
        self.declare_parameter('area_a_x', 3.0)
        self.declare_parameter('area_a_y', 2.0)
        self.declare_parameter('area_a_yaw_deg', 0.0)

        # 작업 구역 B
        self.declare_parameter('area_b_x', 5.0)
        self.declare_parameter('area_b_y', -1.0)
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

        # =========================================================
        # 내부 상태
        # =========================================================
        # WAITING_FOR_START : 시작 버튼 대기
        # MOVING            : 이동 중
        # WAITING           : 목표 도착 후 다음 명령 대기
        # STOPPED           : 정지 상태
        # RETURNING_HOME    : 초기 위치 복귀 중
        # ERROR             : 에러 상태
        self.current_state = "WAITING_FOR_START"

        self.goal_active = False
        self.goal_handle = None
        self.current_goal_name = None
        self.last_movement_command = None   # 마지막 이동 명령 저장
        self.follower_state = "UNKNOWN"

        # =========================================================
        # Pub / Sub
        # =========================================================
        self.state_pub = self.create_publisher(String, '/leader_state', 10)
        self.result_pub = self.create_publisher(String, '/leader_result', 10)

        # TurtleBot4 환경에 따라 /cmd_vel_raw가 맞을 수도 있음
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)

        self.gui_cmd_sub = self.create_subscription(
            String,
            '/leader_cmd',
            self.cmd_callback,
            10
        )

        self.follower_state_sub = self.create_subscription(
            String,
            '/follower_state',
            self.follower_callback,
            10
        )

        # =========================================================
        # Nav2 Action Client
        # =========================================================
        self.action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # =========================================================
        # 주기적 상태 publish
        # =========================================================
        self.state_timer = self.create_timer(0.5, self.publish_state)

        self.get_logger().info("Leader Node 시작")
        self.get_logger().info(
            f"HOME=({self.home_x:.2f}, {self.home_y:.2f}, {self.home_yaw_deg:.1f}deg), "
            f"START=({self.start_x:.2f}, {self.start_y:.2f}, {self.start_yaw_deg:.1f}deg), "
            f"A=({self.area_a_x:.2f}, {self.area_a_y:.2f}, {self.area_a_yaw_deg:.1f}deg), "
            f"B=({self.area_b_x:.2f}, {self.area_b_y:.2f}, {self.area_b_yaw_deg:.1f}deg)"
        )
        self.get_logger().info("현재 상태: WAITING_FOR_START")

    # =========================================================
    # 유틸 함수
    # =========================================================
    def yaw_deg_to_quaternion_zw(self, yaw_deg: float):
        yaw_rad = math.radians(yaw_deg)
        z = math.sin(yaw_rad / 2.0)
        w = math.cos(yaw_rad / 2.0)
        return z, w

    def publish_state(self):
        msg = String()
        msg.data = self.current_state
        self.state_pub.publish(msg)

    def publish_result(self, text: str):
        msg = String()
        msg.data = text
        self.result_pub.publish(msg)

    def stop_cmd_vel(self):
        twist = Twist()
        self.cmd_pub.publish(twist)

    # =========================================================
    # GUI 명령 처리
    # =========================================================
    def cmd_callback(self, msg: String):
        cmd = msg.data.strip().upper()
        self.get_logger().info(f"[GUI CMD] {cmd}")

        # follower가 멈춘 상태면 STOP 외 다른 이동 명령 차단
        if self.follower_state == "STOPPED" and cmd not in ["STOP"]:
            self.get_logger().warn("Follower가 STOPPED 상태라 이동 명령을 무시합니다.")
            return

        # ---------------------------------------------------------
        # 1. 아직 시작 전이면 START만 허용
        # ---------------------------------------------------------
        if self.current_state == "WAITING_FOR_START":
            if cmd == "START":
                self.last_movement_command = "START"
                self.get_logger().info("START 신호 수신 → 시작 지점으로 이동")
                self.start_named_goal(
                    "START_POINT",
                    self.start_x,
                    self.start_y,
                    self.start_yaw_deg
                )
            else:
                self.get_logger().warn("아직 START 전입니다. START 명령만 허용됩니다.")
            return

        # ---------------------------------------------------------
        # 2. 일반 명령 처리
        # ---------------------------------------------------------
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
            self.get_logger().warn("GUI 정지 명령 수신")
            self.stop_robot(reason="GUI_STOP")

        elif cmd == "RESUME_LAST":
            self.resume_last_goal()

        else:
            self.get_logger().warn(f"알 수 없는 명령: {cmd}")

    # =========================================================
    # follower 상태 처리
    # =========================================================
    def follower_callback(self, msg: String):
        new_state = msg.data.strip().upper()
        self.follower_state = new_state

        if new_state == "STOPPED":
            self.get_logger().warn("Follower가 STOPPED 상태 → Leader도 정지")
            self.stop_robot(reason="FOLLOWER_STOPPED")

    # =========================================================
    # Goal 시작
    # =========================================================
    def start_named_goal(self, goal_name: str, x: float, y: float, yaw_deg: float):
        if self.goal_active:
            self.get_logger().warn("이미 goal 진행 중이라 새 명령을 무시합니다.")
            return

        self.send_goal(x, y, yaw_deg, goal_name)

    def send_goal(self, x: float, y: float, yaw_deg: float, goal_name: str):
        if not self.action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("NavigateToPose action server를 찾을 수 없습니다.")
            self.current_state = "ERROR"
            self.publish_state()
            self.publish_result("NAV2_SERVER_NOT_AVAILABLE")
            return

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()

        goal_msg.pose.pose.position.x = float(x)
        goal_msg.pose.pose.position.y = float(y)
        goal_msg.pose.pose.position.z = 0.0

        qz, qw = self.yaw_deg_to_quaternion_zw(yaw_deg)
        goal_msg.pose.pose.orientation.x = 0.0
        goal_msg.pose.pose.orientation.y = 0.0
        goal_msg.pose.pose.orientation.z = qz
        goal_msg.pose.pose.orientation.w = qw

        self.get_logger().info(
            f"Goal 전송: {goal_name} -> x={x:.2f}, y={y:.2f}, yaw={yaw_deg:.1f}"
        )

        self.goal_active = True
        self.current_goal_name = goal_name

        if goal_name == "HOME":
            self.current_state = "RETURNING_HOME"
        else:
            self.current_state = "MOVING"

        self.publish_state()

        send_goal_future = self.action_client.send_goal_async(
            goal_msg,
            feedback_callback=self.feedback_callback
        )
        send_goal_future.add_done_callback(self.goal_response_callback)

    # =========================================================
    # Nav2 콜백
    # =========================================================
    def feedback_callback(self, feedback_msg):
        # 필요 시 이동 거리, 남은 거리 등을 여기서 로그 가능
        pass

    def goal_response_callback(self, future):
        try:
            goal_handle = future.result()
        except Exception as e:
            self.get_logger().error(f"Goal 전송 실패: {e}")
            self.goal_active = False
            self.goal_handle = None
            self.current_state = "ERROR"
            self.publish_state()
            self.publish_result("GOAL_SEND_FAILED")
            return

        if not goal_handle.accepted:
            self.get_logger().error("Goal rejected")
            self.goal_active = False
            self.goal_handle = None

            if self.current_goal_name == "START_POINT":
                self.current_state = "WAITING_FOR_START"
            else:
                self.current_state = "WAITING"

            self.publish_state()
            self.publish_result("GOAL_REJECTED")
            return

        self.goal_handle = goal_handle
        self.get_logger().info("Goal accepted")

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.get_result_callback)

    def get_result_callback(self, future):
        try:
            result = future.result()
        except Exception as e:
            self.get_logger().error(f"Goal 결과 수신 실패: {e}")
            self.goal_active = False
            self.goal_handle = None
            self.current_state = "ERROR"
            self.publish_state()
            self.publish_result("GOAL_RESULT_ERROR")
            return

        status = result.status

        # 주요 status
        # 4: succeeded
        # 5: canceled
        # 6: aborted
        if status == 4:
            self.get_logger().info(f"Goal 도착 완료: {self.current_goal_name}")

            if self.current_goal_name == "START_POINT":
                self.current_state = "WAITING"
                self.publish_result("START_POINT_DONE")

            elif self.current_goal_name == "AREA_A":
                self.current_state = "WAITING"
                self.publish_result("AREA_A_DONE")

            elif self.current_goal_name == "AREA_B":
                self.current_state = "WAITING"
                self.publish_result("AREA_B_DONE")

            elif self.current_goal_name == "HOME":
                self.current_state = "WAITING"
                self.publish_result("HOME_DONE")

            else:
                self.current_state = "WAITING"
                self.publish_result(f"{self.current_goal_name}_DONE")

        elif status == 5:
            self.get_logger().warn(f"Goal 취소됨: {self.current_goal_name}")
            self.current_state = "STOPPED"
            self.publish_result(f"{self.current_goal_name}_CANCELED")

        elif status == 6:
            self.get_logger().error(f"Goal 실패(ABORTED): {self.current_goal_name}")
            self.current_state = "ERROR"
            self.publish_result(f"{self.current_goal_name}_ABORTED")

        else:
            self.get_logger().warn(f"알 수 없는 Goal 종료 상태: {status}")
            self.current_state = "WAITING"
            self.publish_result(f"{self.current_goal_name}_UNKNOWN_STATUS_{status}")

        self.goal_active = False
        self.goal_handle = None
        self.current_goal_name = None
        self.publish_state()

    # =========================================================
    # 정지 / 재개
    # =========================================================
    def stop_robot(self, reason="UNKNOWN"):
        self.get_logger().warn(f"Leader 정지 실행. reason={reason}")

        # Nav2 goal cancel
        if self.goal_handle is not None and self.goal_active:
            try:
                cancel_future = self.goal_handle.cancel_goal_async()
                cancel_future.add_done_callback(self.cancel_done_callback)
            except Exception as e:
                self.get_logger().error(f"Goal cancel 요청 실패: {e}")

        # 속도 0 publish
        self.stop_cmd_vel()

        self.current_state = "STOPPED"
        self.publish_state()
        self.publish_result(f"STOPPED_BY_{reason}")

    def cancel_done_callback(self, future):
        try:
            _ = future.result()
            self.get_logger().info("Goal cancel 요청 완료")
        except Exception as e:
            self.get_logger().error(f"Goal cancel 응답 처리 실패: {e}")

        self.goal_active = False
        self.goal_handle = None

    def resume_last_goal(self):
        if self.goal_active:
            self.get_logger().warn("이미 이동 중이라 RESUME_LAST를 무시합니다.")
            return

        if self.last_movement_command == "START":
            self.get_logger().info("마지막 목표 START_POINT로 재이동")
            self.start_named_goal(
                "START_POINT",
                self.start_x,
                self.start_y,
                self.start_yaw_deg
            )

        elif self.last_movement_command == "GO_TO_A":
            self.get_logger().info("마지막 목표 AREA_A로 재이동")
            self.start_named_goal("AREA_A", self.area_a_x, self.area_a_y, self.area_a_yaw_deg)

        elif self.last_movement_command == "GO_TO_B":
            self.get_logger().info("마지막 목표 AREA_B로 재이동")
            self.start_named_goal("AREA_B", self.area_b_x, self.area_b_y, self.area_b_yaw_deg)

        elif self.last_movement_command == "RETURN_HOME":
            self.get_logger().info("마지막 목표 HOME으로 재이동")
            self.start_named_goal("HOME", self.home_x, self.home_y, self.home_yaw_deg)

        else:
            self.get_logger().warn("재개할 마지막 이동 명령이 없습니다.")

    # =========================================================
    # 종료
    # =========================================================
    def destroy_node(self):
        self.get_logger().info("Leader Node 종료 중...")
        self.stop_cmd_vel()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("KeyboardInterrupt로 종료")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()