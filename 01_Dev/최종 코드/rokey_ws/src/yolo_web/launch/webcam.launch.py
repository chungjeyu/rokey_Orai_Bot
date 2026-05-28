import os
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    package_name = 'yolo_web'

    return LaunchDescription([
        # 노드 A 실행
        Node(
            package=package_name,
            executable='fork_detect_a',
            name='detecting_node_a',
            output='screen',
            parameters=[{'debug': True}]
        ),

        # 노드 B 실행
        Node(
            package=package_name,
            executable='fork_detect_b',
            name='detecting_node_b',
            output='screen',
            parameters=[{'debug': True}]
        ),

        # 클래시파이어 실행
        Node(
            package=package_name,
            executable='truck_fork_classifer',
            name='webcam_trigger_node',
            output='screen',
            parameters=[{'debug': True}]
        ),
    ])