#!/usr/bin/env python3

import time
import threading
import rclpy

from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from std_msgs.msg import Bool, String
from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Navigator,
    TurtleBot4Directions
)


class GuiNavigator(Node):
    """
    GUI에서 목표 지점(A 또는 B)과 시작 신호(True)를 받아
    미리 정의된 A/B 좌표로 이동하는 노드
    """

    def __init__(self):
        super().__init__('gui_ab_navigator')

        # -------------------------------
        # 상태 변수
        # -------------------------------
        self.start_requested = False
        self.started = False
        self.selected_target = None   # 'A' 또는 'B'

        # -------------------------------
        # 미리 정의된 목표 좌표
        # 여기 값을 실제 맵 좌표로 수정하면 됨 
        # -------------------------------
        self.goal_dict = {
            'A': {
                'xy': [1.0, 0.5],
                'direction': TurtleBot4Directions.NORTH
            },
            'B': {
                'xy': [-1.2, 0.8],
                'direction': TurtleBot4Directions.SOUTH
            }
        }

        # -------------------------------
        # GUI 목표 지점 구독
        # 예: "A" 또는 "B"
        # -------------------------------
        self.target_sub = self.create_subscription(
            String,
            '/gui/target_zone',
            self.target_callback,
            10
        )

        # -------------------------------
        # GUI 시작 신호 구독
        # True면 이동 시작
        # -------------------------------
        self.start_sub = self.create_subscription(
            Bool,
            '/gui/start_nav',
            self.start_callback,
            10
        )

        # -------------------------------
        # TurtleBot4 Navigator
        # robot8 네임스페이스를 쓴다면 유지
        # 아니면 namespace 제거
        # -------------------------------
        self.navigator = TurtleBot4Navigator(namespace='/robot4')

        self.get_logger().info('GuiABNavigator 대기 중...')
        self.get_logger().info('/gui/target_zone 에서 A 또는 B를 기다리는 중')
        self.get_logger().info('/gui/start_nav 에서 True 신호를 기다리는 중')

    # ============================================
    # GUI에서 목표 지점(A/B) 수신
    # ============================================
    def target_callback(self, msg: String):
        target = msg.data.strip().upper()

        if target not in self.goal_dict:
            self.get_logger().warn(f'지원하지 않는 목표 지점: {target}')
            return

        self.selected_target = target
        self.get_logger().info(f'목표 지점 선택됨: {self.selected_target}')

    # ============================================
    # GUI에서 시작 신호 수신
    # ============================================
    def start_callback(self, msg: Bool):
        if msg.data:
            self.start_requested = True
            self.get_logger().info('GUI 시작 신호(True) 수신')
        else:
            self.start_requested = False
            self.get_logger().info('GUI 시작 신호(False) 수신')

    # ============================================
    # Nav2 초기화
    # ============================================
    def setup_navigation(self):
        if not self.navigator.getDockedStatus():
            self.navigator.info('Docking before initializing pose')
            self.navigator.dock()

        # 실제 시작 위치가 (0,0), NORTH가 아닐 경우 수정
        initial_pose = self.navigator.getPoseStamped(
            [0.0, 0.0],
            TurtleBot4Directions.NORTH
        )

        self.navigator.clearAllCostmaps()
        self.navigator.setInitialPose(initial_pose)
        self.navigator.waitUntilNav2Active()
        self.navigator.undock()

        self.get_logger().info('Navigation setup complete.')

    # ============================================
    # 현재 선택된 목표(A/B)로 이동
    # ============================================
    def execute_mission(self):
        if self.selected_target is None:
            self.get_logger().warn('선택된 목표 지점이 없음 (A 또는 B 먼저 선택해야 함)')
            return

        if self.selected_target not in self.goal_dict:
            self.get_logger().warn(f'잘못된 목표 지점: {self.selected_target}')
            return

        self.started = True

        goal_info = self.goal_dict[self.selected_target]
        goal_xy = goal_info['xy']
        goal_dir = goal_info['direction']

        goal_pose = self.navigator.getPoseStamped(goal_xy, goal_dir)

        self.get_logger().info(
            f'[{self.selected_target}] 지점으로 이동 시작 -> '
            f'x={goal_xy[0]:.3f}, y={goal_xy[1]:.3f}'
        )

        self.navigator.startToPose(goal_pose)

        while rclpy.ok() and not self.navigator.isTaskComplete():
            time.sleep(0.1)

        self.get_logger().info(f'[{self.selected_target}] 지점 도착 완료 또는 navigation 종료')

        # 상태 초기화
        self.started = False
        self.start_requested = False

    # ============================================
    # 메인 루프
    # ============================================
    def run(self):
        self.setup_navigation()

        while rclpy.ok():
            if self.start_requested and not self.started:
                self.execute_mission()

            time.sleep(0.1)


def main(args=None):
    rclpy.init(args=args)

    node = GuiNavigator()

    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()