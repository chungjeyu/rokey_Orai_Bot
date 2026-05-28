#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Navigator,
    TurtleBot4Directions
)

from my_interfaces.srv import NavigateToZone


class GuiNavServer(Node):
    """
    GUI 클라이언트가 서비스 요청으로 A 또는 B를 보내면
    미리 정의된 좌표로 이동한 뒤 결과를 response로 반환하는 서버 노드
    """

    def __init__(self):
        super().__init__('gui_nav_server')

        # -------------------------------
        # 상태 변수
        # -------------------------------
        self.started = False

        # -------------------------------
        # 미리 정의된 목표 좌표
        # 실제 SLAM 맵 좌표로 수정해야 함
        # -------------------------------
        self.goal_dict = {
            'A': {
                'xy': [-5.35, 1.42],
                'direction': TurtleBot4Directions.NORTH
            },
            'B': {
                'xy': [-2.02, -2.98],
                'direction': TurtleBot4Directions.SOUTH
            }
        }

        # -------------------------------
        # Navigator
        # namespace 환경 아니면 제거
        # -------------------------------
        self.navigator = TurtleBot4Navigator()

        # -------------------------------
        # Service server
        # -------------------------------
        self.srv = self.create_service(
            NavigateToZone,
            '/robot4/navigate_to_zone',
            self.handle_navigate_to_zone
        )

        self.get_logger().info('GuiNavServer ready.')
        self.get_logger().info('Service: /robot4/navigate_to_zone')

        # navigation 초기화는 시작할 때 1번만
        self.setup_navigation()

    # ============================================
    # Nav2 초기화
    # ============================================
    def setup_navigation(self):
        if not self.navigator.getDockedStatus():
            self.navigator.info('Docking before initializing pose')
            self.navigator.dock()

        # 실제 시작 위치가 다르면 수정 필요
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
    # 실제 이동 수행
    # ============================================
    def execute_mission(self, target: str):
        if target not in self.goal_dict:
            return False, f'지원하지 않는 목표 지점: {target}'

        if self.started:
            return False, '이미 다른 navigation 작업이 진행 중입니다.'

        self.started = True

        goal_info = self.goal_dict[target]
        goal_xy = goal_info['xy']
        goal_dir = goal_info['direction']

        goal_pose = self.navigator.getPoseStamped(goal_xy, goal_dir)

        self.get_logger().info(
            f'[{target}] 지점으로 이동 시작 -> '
            f'x={goal_xy[0]:.3f}, y={goal_xy[1]:.3f}'
        )

        self.navigator.startToPose(goal_pose)

        while rclpy.ok() and not self.navigator.isTaskComplete():
            rclpy.spin_once(self, timeout_sec=0.1)

        self.started = False
        self.get_logger().info(f'[{target}] 지점 도착 완료 또는 navigation 종료')

        return True, f'{target} 지점 이동 완료'

    # ============================================
    # 서비스 콜백
    # ============================================
    def handle_navigate_to_zone(self, request, response):
        target = request.zone.strip().upper()
        self.get_logger().info(f'Service request received: zone={target}')

        success, message = self.execute_mission(target)

        response.success = success
        response.message = message
        return response


def main(args=None):
    rclpy.init(args=args)

    node = GuiNavServer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()


#client없이 일단 좌표지점까지 가게하는 CLI
    #ros2 service call /robot8/navigate_to_zone my_interfaces/srv/NavigateToZone "{zone: 'A'}"
    #ros2 service call /robot8/navigate_to_zone my_interfaces/srv/NavigateToZone "{zone: 'B'}"