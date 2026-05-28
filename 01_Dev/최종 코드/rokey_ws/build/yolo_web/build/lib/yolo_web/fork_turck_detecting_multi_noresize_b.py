import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from ultralytics import YOLO
import sys
import threading
import time


class TargetDetectingNode(Node):
    def __init__(self):
        super().__init__('target_detecting_node')

        self.declare_parameter("debug", True)

        # =========================
        # 퍼블리셔 (통합)
        # =========================

        self.img_pub = self.create_publisher(
            CompressedImage,
            'webcam_detected/compressed_image',
            10
        )

        # fork, truck 구분 없이 도착을 알리는 단일 퍼블리셔
        self.arrival_pub = self.create_publisher(
            String,
            'webcam_detected/arrived',
            10
        )

        # =========================
        # YOLO 모델 로드
        # =========================

        model_path = '/home/rokey/rokey_ws/src/yolo_web/yolo_web/wc_last.pt'

        try:
            self.model = YOLO(model_path).to('cuda')
            self.get_logger().info(f"YOLO 클래스: {self.model.names}")
        except Exception as e:
            self.get_logger().error(f"모델 로드 실패: {e}")
            sys.exit(1)

        self.target_classes = ['fork', 'truck']

        # =========================
        # 감지 카운터 (통합)
        # =========================

        self.arrival_counter = 0

        self.threshold = 5
        self.counter_max = 10

        # 1회 발행 제어
        self.arrival_goal_sent = False

        # =========================
        # 카메라
        # =========================

        camera_index = 7
        self.cap = cv2.VideoCapture(camera_index)

        # 최적화 설정 추가
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 15)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # 지연 방지

        if not self.cap.isOpened():
            self.get_logger().error(f"카메라 {camera_index}번을 열 수 없습니다!")
            sys.exit(1)

        self.get_logger().info(f"카메라 {camera_index}번 연결 성공")

        # =========================
        # 멀티스레딩용 변수
        # =========================

        self.frame_lock = threading.Lock()
        self.latest_frame = None
        self.running = True

        # 첫 프레임으로 ROI 생성
        ret, frame = self.cap.read()

        if not ret:
            self.get_logger().error("초기 프레임 읽기 실패")
            sys.exit(1)

        # 웹캠 사이즈 조절 없이 원본 프레임 기준으로 ROI 생성
        h, w = frame.shape[:2]

        self.roi_box = [
            int(w * 0.35),
            int(h * 0.35),
            int(w * 0.65),
            int(h * 0.65)
        ]

        self.get_logger().info(f"ROI 생성 완료: {self.roi_box}")

        with self.frame_lock:
            self.latest_frame = frame.copy()

        # 카메라 프레임 읽기 스레드 시작
        self.capture_thread = threading.Thread(
            target=self.capture_loop,
            daemon=True
        )
        self.capture_thread.start()

        # YOLO 추론 및 publish는 ROS2 timer에서 실행
        self.timer = self.create_timer(0.2, self.run_logic)

    def capture_loop(self):
        while self.running:
            ret, frame = self.cap.read()

            if not ret:
                self.get_logger().warning("카메라 프레임 읽기 실패")
                time.sleep(0.05)
                continue

            with self.frame_lock:
                self.latest_frame = frame.copy()

            time.sleep(0.01)

    def calculate_iou(self, box1, box2):
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter_area = max(0, x2 - x1) * max(0, y2 - y1)

        box1_area = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
        box2_area = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])

        union_area = box1_area + box2_area - inter_area

        return inter_area / union_area if union_area > 0 else 0.0

    def publish_image(self, frame):
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.format = "jpeg"

        success, buffer = cv2.imencode(
            '.jpg',
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 80]
        )

        if success:
            msg.data = buffer.tobytes()
            self.img_pub.publish(msg)
        else:
            self.get_logger().warning("이미지 인코딩 실패")

    def publish_detected_class(self, publisher, message):
        msg = String()
        msg.data = message
        publisher.publish(msg)

    def update_counter(self, detected, counter):
        if detected:
            return min(self.counter_max, counter + 1)

        return max(0, counter - 1)

    def run_logic(self):
        # 카메라 스레드에서 읽은 최신 프레임 가져오기
        with self.frame_lock:
            if self.latest_frame is None:
                self.get_logger().warning("사용 가능한 프레임이 없습니다.")
                return

            frame = self.latest_frame.copy()

        # 웹캠 사이즈 조절 없이 원본 프레임 그대로 YOLO 추론
        results = self.model(frame, conf=0.7, verbose=False)

        roi_box = self.roi_box

        # ROI 표시
        cv2.rectangle(
            frame,
            (roi_box[0], roi_box[1]),
            (roi_box[2], roi_box[3]),
            (0, 0, 255),
            2
        )

        target_condition_met = False
        max_iou = 0.0
        max_conf = 0.0

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]

                if label not in self.target_classes:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])

                yolo_box = [x1, y1, x2, y2]
                iou = self.calculate_iou(yolo_box, roi_box)

                color = (255, 0, 0) if label == 'fork' else (0, 255, 0)

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    color,
                    2
                )

                cv2.putText(
                    frame,
                    f"{label} {conf:.2f}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2
                )

                cv2.putText(
                    frame,
                    f"IOU:{iou:.2f}",
                    (x1, y1 - 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 0),
                    2
                )

                # =========================
                # 통합 조건 검사 (fork 또는 truck)
                # =========================
                max_iou = max(max_iou, iou)
                max_conf = max(max_conf, conf)

                if iou >= 0.25 and conf >= 0.7:
                    target_condition_met = True

        # =========================
        # 통합 카운터 업데이트
        # =========================
        self.arrival_counter = self.update_counter(
            target_condition_met,
            self.arrival_counter
        )

        # =========================
        # 통합 publish 처리
        # =========================
        if self.arrival_counter >= self.threshold and not self.arrival_goal_sent:
            self.get_logger().info(
                f"🎯 타겟(fork/truck) 도착 감지 ({self.threshold}프레임 이상 유지)"
            )

            # "arrived" 라는 문자열 하나만 퍼블리시
            self.publish_detected_class(self.arrival_pub, "arrived")
            self.publish_image(frame)

            self.arrival_goal_sent = True

        if self.arrival_counter == 0:
            self.arrival_goal_sent = False

        # =========================
        # 디버그 화면
        # =========================
        if self.get_parameter("debug").value:
            debug_text_1 = (
                f"ArrivalCnt:{self.arrival_counter} Sent:{self.arrival_goal_sent}"
            )

            debug_text_2 = (
                f"Max_IOU:{max_iou:.2f} Max_Conf:{max_conf:.2f}"
            )

            cv2.putText(
                frame,
                debug_text_1,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

            cv2.putText(
                frame,
                debug_text_2,
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

            cv2.imshow("Webcam Debug", frame)
            cv2.waitKey(1)

    def destroy_node(self):
        # 카메라 스레드 종료
        self.running = False

        if hasattr(self, 'capture_thread') and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)

        if self.cap is not None and self.cap.isOpened():
            self.cap.release()

        cv2.destroyAllWindows()

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)

    node = TargetDetectingNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()