import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge
from ultralytics import YOLO
import os
class WebcamTriggerNode(Node):
    def __init__(self):
        super().__init__('webcam_trigger_node')
        
        # 1. 모델 설정 (절대 경로 사용)
        model_path = '/home/rokey/rokey_ws/src/yolo_web/web_detect/wc_best3.pt'
        self.model = YOLO(model_path)
        self.bridge = CvBridge()
        self.target_class = 'rc_car' 
        
        # 2. 퍼블리셔 설정
        self.img_pub = self.create_publisher(Image, 'webcam/processed_image', 10)
        self.trigger_pub = self.create_publisher(Bool, 'webcam/car_detected', 10)
        
        # 3. 필터링 및 유지력 변수
        self.detection_counter = 0
        self.threshold = 5     # 5프레임 이상 보이면 True
        self.last_signal = False
        
        # 4. 카메라 설정
        self.cap = cv2.VideoCapture(2) 
        if not self.cap.isOpened():
            self.get_logger().error("웹캠을 열 수 없습니다!")
            exit()

        # 5. 주기적 실행 (0.1초 = 10Hz)
        self.timer = self.create_timer(0.1, self.run_logic)
        self.get_logger().info("🚀 웹캠 트리거 노드가 시작되었습니다. (디버그 모드)")

    def run_logic(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        # YOLO 추론 (conf=0.5 정도로 설정하여 너무 낮은 확률은 무시)
        results = self.model(frame, conf=0.5, verbose=False)
        current_frame_detected = False

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]
                
                if label == self.target_class:
                    current_frame_detected = True
                    # 시각화 박스 그리기
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # --- [중요] 디버깅 창 띄우기 ---
        # 실제 박스가 깜빡이는지 여기서 확인하세요.
        cv2.imshow("Webcam Debug", frame)
        cv2.waitKey(1)

        # --- 개선된 노이즈 필터링 로직 ---
        if current_frame_detected:
            # 발견 시 카운터 증가 (최대값 제한)
            self.detection_counter = min(10, self.detection_counter + 1)
        else:
            # 발견 실패 시 바로 0으로 만들지 않고 1씩 감소 (유지력 부여)
            self.detection_counter = max(0, self.detection_counter - 1)

        # 임계값 이상이면 신호 발생
        detected_signal = self.detection_counter >= self.threshold
        
        # 상태 변화 로그 출력
        if detected_signal != self.last_signal:
            if detected_signal:
                self.get_logger().info("🎯 rc_car 포착! 터틀봇에게 신호를 보냅니다.")
            else:
                self.get_logger().info("💤 rc_car가 사라졌습니다.")
            self.last_signal = detected_signal

        # 신호 발행 (Bool)
        msg = Bool()
        msg.data = detected_signal
        self.trigger_pub.publish(msg)

        # ROS2 이미지 메시지 발행
        img_msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        self.img_pub.publish(img_msg)

    def destroy_node(self):
        self.cap.release()
        cv2.destroyAllWindows() # 창 닫기
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    node = WebcamTriggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()