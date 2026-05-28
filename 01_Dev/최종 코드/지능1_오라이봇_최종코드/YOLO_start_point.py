import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from ultralytics import YOLO
from cv_bridge import CvBridge
import sys
import threading


class WebcamTriggerNode(Node):
    def __init__(self):
        super().__init__('webcam_trigger_node')
        self.declare_parameter("debug", True)

        self.bridge = CvBridge()

        # =========================
        # 📡 퍼블리셔
        # =========================
        self.img_pub = self.create_publisher(
            Image,
            'webcam_classed/image_raw',
            10
        )

        self.detection_pub = self.create_publisher(
            String,
            'webcam_classed/detected_object',
            10
        )

        # =========================
        # 🤖 YOLO 모델 로드
        # =========================
        model_path = '/home/rokey/rokey_ws/src/yolo_web/yolo_web/wc_last.pt'
        try:
            self.model = YOLO(model_path)
            self.get_logger().info(f"YOLO 클래스: {self.model.names}")
        except Exception as e:
            self.get_logger().error(f"모델 로드 실패: {e}")
            sys.exit(1)

        # =========================
        # 🎯 설정
        # =========================
        self.target_classes = ['fork', 'truck']
        self.counters = {cls: 0 for cls in self.target_classes}
        self.latched = {cls: False for cls in self.target_classes}
        self.threshold = 5

        # =========================
        # 🎥 카메라 설정
        # =========================
        camera_index = 2
        self.cap = cv2.VideoCapture(camera_index)

        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 15)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not self.cap.isOpened():
            self.get_logger().error(f"카메라 {camera_index}번을 열 수 없습니다!")
            sys.exit(1)

        self.get_logger().info(f"카메라 {camera_index}번 연결 성공")

        # =========================
        # 🔥 멀티스레드 핵심
        # =========================
        self.latest_frame = None
        self.frame_lock = threading.Lock()

        # 📷 캡처 스레드
        self.capture_thread = threading.Thread(
            target=self.capture_loop,
            daemon=True
        )
        self.capture_thread.start()

        # ⏱ YOLO 처리 타이머
        self.timer = self.create_timer(0.2, self.run_logic)

    # =========================
    # 📷 캡처 전용 스레드
    # =========================
    def capture_loop(self):
        while rclpy.ok():
            ret, frame = self.cap.read()
            if not ret:
                continue

            with self.frame_lock:
                self.latest_frame = frame

    # =========================
    # 🤖 YOLO + ROS 처리
    # =========================
    def run_logic(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return
            frame = self.latest_frame.copy()

        # YOLO 추론
        results = self.model(frame, conf=0.75, verbose=False)

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
        # 🔄 이벤트 처리
        # =========================
        for cls in self.target_classes:
            if detected_classes[cls]:
                self.counters[cls] = min(10, self.counters[cls] + 1)
            else:
                self.counters[cls] = 0

            if self.counters[cls] >= self.threshold and not self.latched[cls]:
                self.get_logger().info(f"🚨 {cls} 5회 연속 감지 → 퍼블리시")

                msg = String()
                msg.data = cls
                self.detection_pub.publish(msg)

                self.publish_image(frame)

                self.latched[cls] = True

            if self.counters[cls] == 0:
                self.latched[cls] = False

        # =========================
        # 🖥 디버그
        # =========================
        if self.get_parameter("debug").value:
            debug_texts = [
                f"{cls[0].upper()}:{self.counters[cls]}({self.latched[cls]})"
                for cls in self.target_classes
            ]
            text = " ".join(debug_texts)

            cv2.putText(frame, text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Webcam Debug", frame)
            cv2.waitKey(1)

    # =========================
    # 📡 이미지 퍼블리시
    # =========================
    def publish_image(self, frame):
        try:
            msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
            msg.header.stamp = self.get_clock().now().to_msg()
            self.img_pub.publish(msg)
        except Exception as e:
            self.get_logger().error(f"이미지 퍼블리시 에러: {e}")

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