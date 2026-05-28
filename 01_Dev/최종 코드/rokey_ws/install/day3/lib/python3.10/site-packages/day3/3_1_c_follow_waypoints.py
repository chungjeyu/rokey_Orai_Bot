import rclpy
import time
import math # pi 값을 사용하기 위해 추가
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Directions, TurtleBot4Navigator


def main():
    rclpy.init()

    navigator = TurtleBot4Navigator()

    # Start on dock
    if not navigator.getDockedStatus():
        navigator.info('Docking before intialising pose')
        navigator.dock()

    # Set initial pose
    initial_pose = navigator.getPoseStamped([0.0, 0.0], TurtleBot4Directions.NORTH)
    navigator.setInitialPose(initial_pose)

    # Wait for Nav2
    navigator.waitUntilNav2Active()

    # Set goal poses
    goal_pose = []
    # goal_pose.append(navigator.getPoseStamped([-3.3, 5.9], TurtleBot4Directions.NORTH))
    # goal_pose.append(navigator.getPoseStamped([2.1, 6.3], TurtleBot4Directions.EAST))
    # goal_pose.append(navigator.getPoseStamped([2.0, 1.0], TurtleBot4Directions.SOUTH))
    # goal_pose.append(navigator.getPoseStamped([-1.0, 0.0], TurtleBot4Directions.NORTH))

    goal_pose.append(navigator.getPoseStamped([-0.1668, -0.3049], TurtleBot4Directions.SOUTH))
    goal_pose.append(navigator.getPoseStamped([-1.1943, -0.3740], TurtleBot4Directions.SOUTH))
    goal_pose.append(navigator.getPoseStamped([-1.5589, 1.7090], TurtleBot4Directions.NORTH))
    goal_pose.append(navigator.getPoseStamped([-0.4276, 1.8617], TurtleBot4Directions.NORTH))

    # Undock
    navigator.undock()

    # ====== 웨이포인트 이동 및 360도 회전 로직 ======
    for i, pose in enumerate(goal_pose):
        navigator.info(f'[{i+1}/{len(goal_pose)}] 이동 중...')
        navigator.startToPose(pose)

        # 목적지에 도착할 때까지 대기
        while not navigator.isTaskComplete():
            time.sleep(0.1)

        # 도착 후 360도(2*pi) 제자리 회전 명령
        navigator.info(f'[{i+1}/{len(goal_pose)}] 도착 완료! 360도 회전 시작...')
        navigator.spin(spin_dist=2.0 * math.pi)

        # 회전이 끝날 때까지 대기
        while not navigator.isTaskComplete():
            time.sleep(0.1)
            
    navigator.info('모든 웨이포인트 탐색 및 회전이 완료되었습니다.')
    # ================================================
    # Follow Waypoints
    # navigator.startFollowWaypoints(goal_pose)

    
    # Finished navigating, dock
    navigator.dock()

    rclpy.shutdown()


if __name__ == '__main__':
    main()