import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from sensor_msgs.msg import BatteryState, CompressedImage, Image
import requests
import threading
import cv2
import numpy as np
import os
from datetime import datetime
from flask import Flask, request, jsonify
from cv_bridge import CvBridge
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy 

bridge_app = Flask(__name__)
target_node = None

@bridge_app.route('/emergency_stop', methods=['POST'])
def emergency_stop_api():
    if target_node:
        target_node.publish_emergency_stop()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "msg": "Node not found"}), 500

@bridge_app.route('/move_robot', methods=['POST'])
def move_robot_api():
    area = request.json.get('area')
    target_node.send_move_command(area)
    return jsonify({"status": "success"})

class OraiBridgeNode(Node):
    def __init__(self):
        super().__init__('orai_bridge_node')
        self.bridge = CvBridge()
        self.upload_path = '/home/rokey/06_04_orai_bot_test_0426/static/upload'  # 절대 경로
        os.makedirs(self.upload_path, exist_ok=True)
        self.important_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10
        )

        # 1. 두 로봇의 준비 상태를 추적할 플래그 추가
        self.robot3_ready = False
        self.robot4_ready = False
        self.pending_target_area = None        

        # --- 상태 변수 추가 ---
        self.leader_arrived_target = False  # 리더가 목적지에 도착했는지
        self.cam_detected_target = False    # 웹캠이 로봇을 찾았는지

        self.latest_entry_img_path = None  # 이미지를 먼저 저장하고 경로를 보관할 변수
        self.current_area = ""  # 현재 작업 중인 구역명을 저장하기 위한 변수 추가

        # --- 웹캠 상태 구독 추가 (A/B 분리 및 대문자 통합) ---
        self.create_subscription(String, 'webcam_A/arrived', self.webcam_a_callback, 10)
        self.create_subscription(String, 'webcam_B/arrived', self.webcam_b_callback, 10)
        
        # --- 퍼블리셔 (명령 내리기) ---
        self.cmd_pub4 = self.create_publisher(String, '/leader_cmd', self.important_qos)   
        self.move_pub4 = self.create_publisher(String, '/leader_cmd', self.important_qos)    

        # --- 서브스크라이버 (터틀봇 말 듣기) ---
        self.create_subscription(String, 'robot3/follower_result', self.robot3_status_callback, 10)    
        self.create_subscription(String, 'robot4/leader_result', self.robot4_status_callback, 10)      

        # 토픽 구독 설정
        self.create_subscription(BatteryState, 'robot3/battery_status', 
                         lambda msg: self.battery_callback(msg, 'robot3'), 10)   
        self.create_subscription(BatteryState, 'robot4/battery_status', 
                         lambda msg: self.battery_callback(msg, 'robot4'), 10)   
        self.create_subscription(Image, 'webcam_classed/image_raw', self.entry_img_callback, 10)  
        self.create_subscription(String, 'webcam_classed/detected_object', self.entry_msg_callback, 10)  
        self.create_subscription(String, '/yolo/detection_status', self.emergency_msg_callback, self.important_qos)  
        self.create_subscription(Image, '/yolo/alert_image', self.emergency_img_callback, self.important_qos)  
        self.create_subscription(Image, 'webcam_detected/compressed_image', self.arrival_img_callback, 10)    

        # 비상정지용 Publisher 생성
        self.stop_pub = self.create_publisher(String, '/emergency_stop', 10)    

    def update_status(self, status_text):
        try:
            requests.post("http://localhost:5000/api/update_robot_status", 
                          json={"status": status_text}, timeout=0.5)
            self.get_logger().info(f"📊 상태 변경: {status_text}")
        except Exception as e:
            self.get_logger().error(f"상태 업데이트 실패: {e}")

    def save_image(self, msg, prefix):
        try:
            # CvBridge를 사용하여 ROS Image 메시지를 OpenCV 포맷(bgr8)으로 변환
            img = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            filename = f"{prefix}_{datetime.now().strftime('%H%M%S')}.jpg"
            filepath = os.path.join(self.upload_path, filename)
            cv2.imwrite(filepath, img)
            return f"/static/upload/{filename}"
        except Exception as e:
            print(f"이미지 저장 오류: {e}")
            return None

    def battery_callback(self, msg, robot_id):
        bat = int(msg.percentage * 100)
        try: 
            requests.post("http://localhost:5000/api/update_robot_status", 
                      json={f"{robot_id}_bat": bat}, timeout=0.1)
        except: pass

    def entry_img_callback(self, msg):
        path = self.save_image(msg, "entry")
        if path:
            self.latest_entry_img_path = path
            self.get_logger().info(f"📸 입차 이미지 저장 완료: {path}")

    def entry_msg_callback(self, msg):
        detected_class = msg.data  
        img_path = self.latest_entry_img_path or "" 
        
        self.get_logger().info(f"🚨 입차 감지: {detected_class}")
        self.update_status("[연결 확인 중]")
        
        try:
            requests.post("http://localhost:5000/api/detect_object", 
                          json={"class": detected_class, "img_path": img_path}, 
                          timeout=1)
            requests.post("http://localhost:5000/api/log_event", 
                          json={"type": "입차", "content": f"{detected_class} 차량 진입 감지", "img_path": img_path}, 
                          timeout=1)
        except Exception as e:
            self.get_logger().error(f"서버 전송 에러: {e}")

    def emergency_msg_callback(self, msg):
        try: requests.post("http://localhost:5000/api/log_event", json={"type": "EMERGENCY", "content": msg.data}, timeout=1)
        except: pass

    def emergency_img_callback(self, msg):
        path = self.save_image(msg, "emergency")
        try: requests.post("http://localhost:5000/api/log_event", json={"type": "EMERGENCY", "content": "긴급 증거 사진", "img_path": path}, timeout=1)
        except: pass

    def arrival_msg_callback(self, msg): pass 

    def arrival_img_callback(self, msg):
        path = self.save_image(msg, "arrival")
        try: requests.post("http://localhost:5000/api/log_event", json={"type": "ARRIVAL", "content": "목적지 도착 및 인증 완료", "img_path": path}, timeout=1)
        except: pass

    def webcam_a_callback(self, msg):
        if msg.data.lower() == "arrived" and self.current_area == "GO_TO_A":
            self.get_logger().info("📷 [A구역] 웹캠: 로봇 인식 완료!")
            self.cam_detected_target = True
            self.check_and_return_home()

    def webcam_b_callback(self, msg):
        if msg.data.lower() == "arrived" and self.current_area == "GO_TO_B":
            self.get_logger().info("📷 [B구역] 웹캠: 로봇 인식 완료!")
            self.cam_detected_target = True
            self.check_and_return_home()

    def send_move_command(self, area):
        # 🌟 핵심 추가: 엑셀의 'a', 'b'를 로봇 명령어 'GO_TO_A', 'GO_TO_B'로 자동 매핑
        area_upper = str(area).strip().upper() 
        
        if area_upper == "A" or "A" in area_upper:
            mapped_cmd = "GO_TO_A"
        elif area_upper == "B" or "B" in area_upper:
            mapped_cmd = "GO_TO_B"
        else:
            mapped_cmd = area_upper 

        # 목적지를 임시 저장
        self.pending_target_area = mapped_cmd
        self.current_area = mapped_cmd 
        
        self.robot3_ready = False
        self.robot4_ready = False
        self.update_status("[대기 중]")
        
        # 터틀봇 정렬(START) 신호 전송
        align_msg = String()
        align_msg.data = "START" 
        self.cmd_pub4.publish(align_msg)
        
        self.get_logger().info(f"목적지 [{mapped_cmd}] 임시 저장 완료. 로봇 4에 정렬(ALIGN) 명령 전송!")

        self.leader_arrived_target = False
        self.cam_detected_target = False

    def robot3_status_callback(self, msg):
        if msg.data == "ARRIVED_START":
            self.robot3_ready = True
            self.get_logger().info("로봇 3 정렬 완료 확인.")
            self.check_and_send_goal()

    def robot4_status_callback(self, msg):
        if msg.data == "ARRIVED_START":
            self.robot4_ready = True
            self.get_logger().info("로봇 4 정렬 완료 확인.")
            self.check_and_send_goal()

        elif msg.data in ["ARRIVED_GO_TO_A", "ARRIVED_GO_TO_B"]:
            self.get_logger().info("🚀 리더: 목적지 도착 완료!")
            self.leader_arrived_target = True
            self.check_and_return_home() 

    def check_and_send_goal(self):
        if self.robot3_ready and self.robot4_ready and self.pending_target_area is not None:
            self.get_logger().info(f"전원 정렬 완료! 목적지 [{self.pending_target_area}] 전송합니다.")
            self.update_status(f"['{self.current_area}'로 이동 중]")

            goal_msg = String(data=self.pending_target_area)
            self.move_pub4.publish(goal_msg)
            
            try:
                requests.post("http://localhost:5000/api/update_robot_status", 
                              json={"status": f"{self.pending_target_area} 구역 호송 이동 중"}, timeout=0.5)
            except: pass
            
            self.pending_target_area = None
            self.robot3_ready = False
            self.robot4_ready = False

    def check_and_return_home(self):
        if self.leader_arrived_target and self.cam_detected_target:
            self.get_logger().info("✅ [완료] 도착+인식 모두 확인. 복귀 명령 전송!")
            self.update_status(f"['{self.current_area}'에 도착, 홈으로 이동]")
            
            home_msg = String(data="GO_TO_HOME")
            self.move_pub4.publish(home_msg)
            
            self.leader_arrived_target = False
            self.cam_detected_target = False

    def publish_emergency_stop(self):
        msg = String()
        msg.data = "STOP"
        self.stop_pub.publish(msg)
        
        self.get_logger().warn("🚨 [EMERGENCY] 비상 정지 명령 발행됨: STOP : 비상 정지!!")
        try:
            requests.post("http://localhost:5000/api/update_robot_status", 
                          json={"status": "🚨 비상 정지 상태 🚨"}, timeout=0.5)
        except: pass

def main(args=None):
    global target_node
    rclpy.init(args=args)
    target_node = OraiBridgeNode()
    t = threading.Thread(target=lambda: bridge_app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False))
    t.daemon = True
    t.start()
    try: rclpy.spin(target_node)
    except KeyboardInterrupt: pass
    finally: 
        if rclpy.ok():
            target_node.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()
