#!/usr/bin/env python3
# source : https://gemini.google.com/share/d9645cc885e7
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.duration import Duration
from rclpy.qos import qos_profile_sensor_data

import cv2
import numpy as np
import math
import threading
import time

# ROS 2 메시지 및 서비스 타입
from std_srvs.srv import SetBool
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, PoseStamped
from cv_bridge import CvBridge

# TF2 (좌표계 변환)
from tf2_ros import Buffer, TransformListener
from tf2_geometry_msgs.tf2_geometry_msgs import do_transform_point

# TurtleBot4 네비게이터
from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator

def euler_to_quaternion(yaw):
    """Yaw(회전각)를 쿼터니언(Quaternion)으로 변환하는 헬퍼 함수"""
    q = [0.0, 0.0, 0.0, 0.0]
    q[2] = math.sin(yaw / 2.0)
    q[3] = math.cos(yaw / 2.0)
    return q

class NodeCApproach(Node):
    def __init__(self):
        super().__init__('node_c_approach')

        # -------------------------------------------------
        # 상태 변수
        # -------------------------------------------------
        self.is_active = False           # Node A가 활성화해주기 전까지는 대기
        self.is_moving = False           # 목표물로 이동 중인지 확인하는 플래그
        self.bridge = CvBridge()
        
        self.depth_image = None
        self.camera_K = None             # 카메라 내부 파라미터 (초점 거리 등)
        self.lock = threading.Lock()     # 스레드 충돌 방지용 락

        # -------------------------------------------------
        # 서비스 서버: Node A가 호출할 활성화 서비스
        # -------------------------------------------------
        self.srv = self.create_service(
            SetBool, 
            '/robot8/node_c_enable', 
            self.enable_callback
        )

        # -------------------------------------------------
        # 구독자 (Subscribers)
        # -------------------------------------------------
        # 1. 카메라 정보 (Intrinsic Matrix 획득용)
        self.sub_info = self.create_subscription(
            CameraInfo,
            '/robot8/oakd/rgb/camera_info',
            self.camera_info_callback,
            10
        )

        # 2. 깊이(Depth) 이미지
        self.sub_depth = self.create_subscription(
            Image,
            '/robot8/oakd/stereo/image_raw',
            self.depth_callback,
            10
        )

        # 3. Node B(YOLO)가 보내는 2D 픽셀 좌표 (u, v)
        self.sub_detection = self.create_subscription(
            PointStamped,
            '/robot8/detection',
            self.detection_callback,
            qos_profile_sensor_data
        )

        # -------------------------------------------------
        # 좌표 변환 (TF2) 설정
        # -------------------------------------------------
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)

        # -------------------------------------------------
        # Turtlebot4 네비게이터 초기화
        # -------------------------------------------------
        self.navigator = TurtleBot4Navigator(namespace='/robot8')
        
        self.get_logger().info("Node C (Approach) 대기 중... Node A의 호출을 기다립니다.")

    # =====================================================
    # Node A 활성화 요청 콜백
    # =====================================================
    def enable_callback(self, request, response):
        """Node A가 '/robot8/node_c_enable' 서비스를 True로 호출하면 실행됨"""
        if request.data:
            self.is_active = True
            response.success = True
            response.message = "Node C Activated! Waiting for target depth."
            self.get_logger().info('Node C 활성화! 목표물 추적 준비 완료.')
        else:
            self.is_active = False
            response.success = True
            response.message = "Node C Deactivated."
            
        return response

    # =====================================================
    # 카메라 파라미터 저장
    # =====================================================
    def camera_info_callback(self, msg):
        """카메라 정보를 한 번만 받아서 3D 변환에 사용할 K 행렬 저장"""
        if self.camera_K is None:
            self.camera_K = np.array(msg.k).reshape(3, 3)
            self.get_logger().info("카메라 Intrinsic Matrix 설정 완료.")

    # =====================================================
    # Depth 이미지 실시간 갱신
    # =====================================================
    def depth_callback(self, msg):
        """가장 최신의 깊이 이미지를 저장해둠"""
        try:
            with self.lock:
                # 16비트 깊이 이미지를 OpenCV 포맷으로 변환 (단위: mm)
                self.depth_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='passthrough')
        except Exception as e:
            self.get_logger().error(f"Depth 변환 에러: {e}")

    # =====================================================
    # 핵심 로직: Node B의 좌표 수신 -> 3D 계산 -> 이동
    # =====================================================
    def detection_callback(self, msg):
        """Node B로부터 (u, v)를 받아 3D 좌표를 구하고 이동"""
        
        # 1. 방어 로직: Node C가 비활성화 상태이거나, 이미 로봇이 목표로 이동 중이면 무시
        if not self.is_active or self.is_moving:
            return

        with self.lock:
            # 아직 데이터가 준비 안 된 경우 대기
            if self.depth_image is None or self.camera_K is None:
                return

            # Node B가 보낸 픽셀 좌표
            u = int(msg.point.x)
            v = int(msg.point.y)

            # 이미지 범위를 벗어나는지 확인
            h, w = self.depth_image.shape
            if u < 0 or u >= w or v < 0 or v >= h:
                self.get_logger().warn("좌표가 이미지 범위를 벗어났습니다.")
                return

            # 해당 픽셀의 깊이(Z) 값 추출 (단위 변환: mm -> m)
            z_m = float(self.depth_image[v, u]) / 1000.0

        # 깊이가 0이거나 너무 멀면 에러(노이즈)로 간주
        if z_m <= 0.1 or z_m > 5.0:
            return

        self.get_logger().info(f"타겟 인식 완료! (픽셀: {u}, {v}), 거리: {z_m:.2f}m")
        
        # 2. 3D 좌표 변환 진행 (네비게이션은 스레드로 분리하여 ROS 콜백 차단 방지)
        self.is_moving = True
        approach_thread = threading.Thread(
            target=self.calculate_and_move,
            args=(u, v, z_m, msg.header.frame_id)
        )
        approach_thread.start()

    def calculate_and_move(self, u, v, z, camera_frame):
        """3D 좌표 변환 및 네비게이션 목표 전송"""
        
        # [Step 1] 픽셀(u,v)과 깊이(Z)를 이용해 카메라 좌표계 상의 (X, Y, Z) 도출
        fx, fy = self.camera_K[0, 0], self.camera_K[1, 1]
        cx, cy = self.camera_K[0, 2], self.camera_K[1, 2]

        X = (u - cx) * z / fx
        Y = (v - cy) * z / fy
        Z = z

        # [Step 2] 카메라 좌표계의 점을 'map' 좌표계로 변환하기 위해 PointStamped 객체 생성
        point_cam = PointStamped()
        point_cam.header.frame_id = camera_frame
        point_cam.header.stamp = self.get_clock().now().to_msg()
        point_cam.point.x = X
        point_cam.point.y = Y
        point_cam.point.z = Z

        try:
            # 카메라 프레임 -> 맵 프레임 변환
            point_map = self.tf_buffer.transform(point_cam, 'map', timeout=Duration(seconds=1.0))
        except Exception as e:
            self.get_logger().error(f"TF 변환 실패: {e}")
            self.is_moving = False
            return

        obj_x = point_map.point.x
        obj_y = point_map.point.y

        # [Step 3] 로봇 현재 위치 가져오기
        robot_pose = self.navigator.getRobotPose()
        if robot_pose is None:
            self.get_logger().error("로봇의 현재 위치를 가져올 수 없습니다.")
            self.is_moving = False
            return

        rx = robot_pose.pose.position.x
        ry = robot_pose.pose.position.y

        # [Step 4] 물체에서 로봇 방향으로 50cm(0.5m) 오프셋 계산
        # 1) 로봇과 물체 사이의 거리(벡터) 계산
        dx = obj_x - rx
        dy = obj_y - ry
        distance = math.sqrt(dx**2 + dy**2)

        offset = 0.5  # 50cm

        if distance <= offset:
            self.get_logger().info("로봇이 이미 목표물 50cm 이내에 있습니다!")
            self.is_active = False # 임무 완료
            self.is_moving = False
            return

        # 2) 50cm 떨어진 목표 X, Y 좌표 계산 (비율 활용)
        ratio = (distance - offset) / distance
        goal_x = rx + dx * ratio
        goal_y = ry + dy * ratio

        # 3) 로봇이 물체를 바라보도록 회전각(Yaw) 계산
        yaw = math.atan2(dy, dx)
        q = euler_to_quaternion(yaw)

        # [Step 5] Nav2에 전송할 Goal Pose 생성
        goal_pose = PoseStamped()
        goal_pose.header.frame_id = 'map'
        goal_pose.header.stamp = self.get_clock().now().to_msg()
        goal_pose.pose.position.x = goal_x
        goal_pose.pose.position.y = goal_y
        goal_pose.pose.orientation.x = q[0]
        goal_pose.pose.orientation.y = q[1]
        goal_pose.pose.orientation.z = q[2]
        goal_pose.pose.orientation.w = q[3]

        self.get_logger().info(f"이동 명령: X={goal_x:.2f}, Y={goal_y:.2f} (물체 앞 50cm)")

        # [Step 6] 해당 위치로 이동
        self.navigator.startToPose(goal_pose)

        while rclpy.ok() and not self.navigator.isTaskComplete():
            time.sleep(0.5)

        # 이동 완료 처리
        result = self.navigator.getResult()
        self.get_logger().info("목표 지점 접근 완료! Node C 임무 종료.")
        
        # 완전 종료를 위해 플래그 초기화
        self.is_active = False
        self.is_moving = False


def main(args=None):
    rclpy.init(args=args)
    node = NodeCApproach()
    
    # GUI 및 여러 콜백(서비스, 구독)이 동시에 돌 수 있도록 MultiThreadedExecutor 사용
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()