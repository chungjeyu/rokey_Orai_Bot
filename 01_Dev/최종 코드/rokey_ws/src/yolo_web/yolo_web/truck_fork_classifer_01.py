import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from ultralytics import YOLO
import sys


class WebcamTriggerNode(Node):
    def __init__(self):
        super().__init__('webcam_trigger_node')
        self.declare_parameter("debug", True)

        # =========================
        # 📡 퍼블리셔 정의
        # =========================

        # 이미지 퍼블리셔 (Image 타입으로 변경, 토픽 이름 변경)
        self.img_pub = self.create_publisher(
            Image,
            'webcam_classed/compressed_image',  # 퍼블리셔 코드에서는 'webcam_classed/compressed_image'로 발행하지만, 구독에서는 'webcam_classed/image_raw'로 구독 --- IGNORE ---
            10
        )
        
        # 통합된 감지 결과 퍼블리셔 (String 타입)
        # 토픽 이름 : webcam_classed/detected_object
        self.detection_pub = self.create_publisher(
            String,
            'webcam_classed/detected_object',
            10
        )

        # YOLO 모델 로드
        model_path = '/home/rokey/rokey_ws/src/yolo_web/yolo_web/wc_last.pt'
        try:
            self.model = YOLO(model_path)
            self.get_logger().info(f"YOLO 클래스: {self.model.names}")
        except Exception as e:
            self.get_logger().error(f"모델 로드 실패: {e}")
            sys.exit(1)

        # 탐지해야할 클래스 지정
        self.target_classes = ['fork', 'truck']

        # 클래스별 카운터 및 Latch(발행 여부)를 딕셔너리로 통합 관리
        self.counters = {cls: 0 for cls in self.target_classes}
        self.latched = {cls: False for cls in self.target_classes}

        # 이벤트 발생 기준 (5번 연속 감지)
        self.threshold = 5

        # 사용할 카메라 인덱스
        camera_index = 2
        self.cap = cv2.VideoCapture(camera_index)

        # 최적화 설정 추가
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 15)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            self.get_logger().error(f"카메라 {camera_index}번을 열 수 없습니다!")
            sys.exit(1)

        self.get_logger().info(f"카메라 {camera_index}번 연결 성공")
        self.timer = self.create_timer(0.2, self.run_logic)

    def run_logic(self):
        ret, frame = self.cap.read()
        if not ret:
            return
            
        # frame = cv2.resize(frame, (640, 480))

        # =========================
        # 🤖 YOLO 추론
        # =========================
        results = self.model(frame, conf=0.75, verbose=False)

        # 클래스별 감지 여부 초기화
        detected_classes = {cls: False for cls in self.target_classes}

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]

                if label in self.target_classes:
                    detected_classes[label] = True

                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    color = (0, 255, 0) if label == 'truck' else (255, 0, 0)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # =========================
        # 🔄 카운터 업데이트 및 이벤트 처리
        # =========================
        for cls in self.target_classes:
            # 해당 클래스 연속 감지 카운트
            if detected_classes[cls]:
                self.counters[cls] = min(10, self.counters[cls] + 1)
            else:
                self.counters[cls] = 0

            # threshold(5) 이상 달성 + 아직 퍼블리시 안 했을 때
            if self.counters[cls] >= self.threshold and not self.latched[cls]:
                self.get_logger().info(f"🚨 {cls} 5회 연속 감지 → 퍼블리시")

                # String 타입으로 클래스 이름만 전송
                msg = String()
                msg.data = cls  # 예: "truck" 또는 "fork"
                self.detection_pub.publish(msg)

                # 이미지도 같이 전송
                self.publish_image(frame)

                # 중복 발행을 막기 위해 래치(Latch) 걸기
                self.latched[cls] = True

            # 화면에서 해당 물체가 사라지면(카운터 0) 래치 해제
            if self.counters[cls] == 0:
                self.latched[cls] = False

        # 디버그 화면
        if self.get_parameter("debug").value:
            # 딕셔너리를 바탕으로 T:5(True) F:0(False) 형태의 텍스트 자동 생성
            debug_texts = [f"{cls[0].upper()}:{self.counters[cls]}({self.latched[cls]})" for cls in self.target_classes]
            text = " ".join(debug_texts)
            
            cv2.putText(frame, text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Webcam Debug", frame)
            cv2.waitKey(1)

    def publish_image(self, frame):
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        
        # OpenCV 프레임 크기 및 인코딩 정보 설정
        msg.height = frame.shape[0]
        msg.width = frame.shape[1]
        msg.encoding = 'bgr8'
        msg.is_bigendian = 0
        msg.step = frame.shape[1] * 3
        
        # 압축 없이 원본 byte 데이터 삽입
        msg.data = frame.tobytes()
        
        self.img_pub.publish(msg)

    def destroy_node(self):
        if self.cap is not None and self.cap.isOpened():
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