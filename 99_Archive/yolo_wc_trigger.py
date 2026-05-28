import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge
from ultralytics import YOLO
import sys

class WebcamTriggerNode(Node):
    def __init__(self):
        super().__init__('webcam_trigger_node')
        
        # 퍼블리셔 선언 (순서를 앞으로 당겨서 확실히 초기화되게 합니다)
        self.img_pub = self.create_publisher(Image, 'webcam/processed_image', 10)
        self.trigger_pub = self.create_publisher(Bool, 'webcam/car_detected', 10)
        
        # 모델 설정 (절대 경로)
        model_path = '/home/rokey/rokey_ws/src/miniproject/wc_best3.pt'
        try:
            self.model = YOLO(model_path)
        except Exception as e:
            self.get_logger().error(f"모델 로드 실패: {e}")
            sys.exit(1)

        self.bridge = CvBridge()
        self.target_class = 'rc_car'
        
        # 필터링 변수
        self.detection_counter = 0
        self.threshold = 5
        self.last_signal = False
        
        # 카메라 설정 (인덱스 2번)
        self.cap = cv2.VideoCapture(2)
        if not self.cap.isOpened():
            self.get_logger().error("웹캠을 열 수 없습니다!")
            sys.exit(1)

        # 타이머 설정 (10Hz)
        self.timer = self.create_timer(0.1, self.run_logic)
        self.get_logger().info("🚀 웹캠 트리거 노드가 시작되었습니다.")

    def run_logic(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        results = self.model(frame, conf=0.5, verbose=False)
        current_frame_detected = False

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]
                
                if label == self.target_class:
                    current_frame_detected = True
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{label}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 디버그 창
        cv2.imshow("Webcam Debug", frame)
        cv2.waitKey(1)

        # 필터링 로직
        if current_frame_detected:
            self.detection_counter = min(10, self.detection_counter + 1)
        else:
            self.detection_counter = max(0, self.detection_counter - 1)

        detected_signal = self.detection_counter >= self.threshold
        
        if detected_signal != self.last_signal:
            if detected_signal:
                self.get_logger().info("🎯 rc_car 포착!")
            else:
                self.get_logger().info("💤 rc_car가 사라졌습니다.")
            self.last_signal = detected_signal

        # 메시지 발행
        msg = Bool()
        msg.data = detected_signal
        self.trigger_pub.publish(msg)

        img_msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
        self.img_pub.publish(img_msg)

    def destroy_node(self):
        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
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

