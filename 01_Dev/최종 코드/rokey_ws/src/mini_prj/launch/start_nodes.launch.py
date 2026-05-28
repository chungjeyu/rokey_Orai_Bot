from launch import LaunchDescription
from launch_ros.actions import Node




def generate_launch_description():


   return LaunchDescription([


       Node(
           package='mini_prj',
           executable='node_a_nav_2_4',
           name='node_a_nav_2_4'
       ),


       Node(
           package='mini_prj',
           executable='node_b_6',
           name='node_b_6'
       ),


   ])
