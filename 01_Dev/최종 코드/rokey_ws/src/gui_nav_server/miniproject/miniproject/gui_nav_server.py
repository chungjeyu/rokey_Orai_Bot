#!/usr/bin/env python3

import rclpy
from rclpy.node import Node

from turtlebot4_navigation.turtlebot4_navigator import (
    TurtleBot4Navigator,
    TurtleBot4Directions
)

from nav2_simple_commander.robot_navigator import TaskResult
from my_interfaces.srv import NavigateToZone


class GuiNavServer(Node):
    def __init__(self):
        super().__init__('gui_nav_server')

        self.started = False

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

        self.navigator = TurtleBot4Navigator(namespace='/robot4')

        self.srv = self.create_service(
            NavigateToZone,
            '/robot4/navigate_to_zone',
            self.handle_navigate_to_zone
        )

        self.get_logger().info('GuiNavServer ready.')
        self.get_logger().info('Service: /robot4/navigate_to_zone')

        self.setup_navigation()

    def setup_navigation(self):
        initial_pose = self.navigator.getPoseStamped(
            [0.0, 0.0],
            TurtleBot4Directions.NORTH
        )

        self.navigator.setInitialPose(initial_pose)
        self.navigator.waitUntilNav2Active()
        self.navigator.clearAllCostmaps()

        self.get_logger().info('Navigation setup complete.')

    def execute_mission(self, target: str):
        if target not in self.goal_dict:
            return False, f'지원하지 않는 목표 지점: {target}'

        if self.started:
            return False, '이미 다른 navigation 작업이 진행 중입니다.'

        self.started = True

        try:
            goal_info = self.goal_dict[target]
            goal_xy = goal_info['xy']
            goal_dir = goal_info['direction']
            goal_pose = self.navigator.getPoseStamped(goal_xy, goal_dir)

            self.get_logger().info(
                f'[{target}] goal start: x={goal_xy[0]:.3f}, y={goal_xy[1]:.3f}'
            )

            self.navigator.goToPose(goal_pose)

            while not self.navigator.isTaskComplete():
                feedback = self.navigator.getFeedback()
                if feedback:
                    self.get_logger().info('이동 중...')

            result = self.navigator.getResult()

            if result == TaskResult.SUCCEEDED:
                return True, f'{target} 지점 도착 성공'
            elif result == TaskResult.CANCELED:
                return False, f'{target} 지점 이동 취소'
            elif result == TaskResult.FAILED:
                return False, f'{target} 지점 이동 실패'
            else:
                return False, f'{target} 지점 결과를 알 수 없음'

        except Exception as e:
            return False, f'예외 발생: {str(e)}'

        finally:
            self.started = False

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
