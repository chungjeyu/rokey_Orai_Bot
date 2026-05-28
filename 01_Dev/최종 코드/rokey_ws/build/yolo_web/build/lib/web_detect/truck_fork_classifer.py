import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool
from ultralytics import YOLO
import sys


class WebcamTriggerNode(Node):
    def __init__(self):
        # ROS2 노드 이름 설정
        super().__init__('webcam_trigger_node')
        # 디버그 표시 여부를 파라미터로 선언
        # 기본값 True
        self.declare_parameter("debug", True)

        # =========================
        # 📡 퍼블리셔 정의
        # =========================

        # 퍼블리셔 (감지 성공시 publishing)
        # 토픽 이름 : webcam_classd/compressed_image'
        # 토픽 타입 : CompressedImage
        # 최근 프라임 10 보존
        self.img_pub = self.create_publisher(
            CompressedImage,
            'webcam_classd/compressed_image',
            10
        )
        # 퍼블리셔 (감지 성공시 publishing)
        # 토픽 이름 : webcam_classed/truck_detected
        # 토픽 타입 : Bool
        # 최근 프라임 10 보존
        self.truck_pub = self.create_publisher(
            Bool,
            'webcam_classed/truck_detected',
            10
        )

        # 퍼블리셔 (감지 성공시 publishing)
        # 토픽 이름 : webcam_classed/fork_detected
        # 토픽 타입 : Bool
        # 최근 프라임 10 보존
        self.fork_pub = self.create_publisher(
            Bool,
            'webcam_classed/fork_detected',
            10
        )

        # YOLO 모델 로드
        model_path = '/home/rokey/truck_fork_classifer/nagative2_best.pt'
        # 클래스 이름 출력
        try:
            self.model = YOLO(model_path)
            self.get_logger().info(f"YOLO 클래스: {self.model.names}")
        # 모델 로드 실패 시 에러 로그 출력 후 종료
        except Exception as e:
            self.get_logger().error(f"모델 로드 실패: {e}")
            sys.exit(1)

        # 탐지해야할 클래스 지정
        self.target_classes = ['fork', 'truck']

        # truck_counter : 트럭 프레임 몃 번 연속적으로 찍하는지 카운트
        # trhreshold 이상일시 img_pub, trigger_pub publishing
        self.truck_counter = 0
        self.fork_counter = 0

        # 이벤트 발생 기준 (5번 연속 감지)
        self.threshold = 5

        # 이미 publish 했는지 여부
        self.truck_latched = False
        self.fork_latched = False

        # 사용할 카메라 인덱스
        camera_index = 0
        self.cap = cv2.VideoCapture(camera_index)
        # cli argumnet 실행서 받아오는 코드
        if not self.cap.isOpened():
            # 카메라 열기 실패 시 종료
            self.get_logger().error(f"카메라 {camera_index}번을 열 수 없습니다!")
            sys.exit(1)

        self.get_logger().info(f"카메라 {camera_index}번 연결 성공")
        # 타이머 설행 
        self.timer = self.create_timer(0.2, self.run_logic)

    def run_logic(self):
        # 카메라가 실제로 프레임을 읽는지 확인
        ret, frame = self.cap.read()
        if not ret:
            return
        # 설계상 계속 돌아가는 부분이 없었음
        # 이미지 크기를 640x480으로 고정 크기가 클수록 yolo 추론시간이 크기 때문
        frame = cv2.resize(frame, (640, 480))

        # =========================
        # 🤖 YOLO 추론
        # =========================
        results = self.model(frame, conf=0.8, verbose=False)

        # 클래스별 감지 여부 초기화
        detected_classes = {cls: False for cls in self.target_classes}

        # 결과 순회
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                label = self.model.names[cls_id]

                # 관심 클래스만 처리
                if label in self.target_classes:
                    detected_classes[label] = True

                    # 바운딩 박스 좌표
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    # 색상 (truck=초록, fork=파랑)
                    color = (0, 255, 0) if label == 'truck' else (255, 0, 0)

                    # 박스 + 라벨 표시
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # 현재 감지 상태
        truck_detected = detected_classes.get('truck', False)
        fork_detected = detected_classes.get('fork', False)


        # 카운터 업데이트
        # truck 연속 감지
        if truck_detected:
            self.truck_counter = min(10, self.truck_counter + 1)
        else:
            self.truck_counter = 0

        # fork 연속 감지
        if fork_detected:
            self.fork_counter = min(10, self.fork_counter + 1)
        else:
            self.fork_counter = 0

        # =========================
        # 🚚 truck 이벤트 처리
        # =========================

        # threshold 이상 + 아직 publish 안했을 때
        if self.truck_counter >= self.threshold and not self.truck_latched:
            self.get_logger().info("🚚 truck 5회 감지 → 1회 publish")

            msg = Bool()
            msg.data = True
            self.truck_pub.publish(msg)

            # 이미지도 같이 전송
            self.publish_image(frame)

            # 다시 publish 안되도록 latch
            self.truck_latched = True

        # 감지 끊기면 latch 해제
        if self.truck_counter == 0:
            self.truck_latched = False

        # fork 이벤트 처리
        if self.fork_counter >= self.threshold and not self.fork_latched:
            self.get_logger().info("🍴 fork 5회 감지 → 1회 publish")

            msg = Bool()
            msg.data = True
            self.fork_pub.publish(msg)

            self.publish_image(frame)

            self.fork_latched = True

        if self.fork_counter == 0:
            self.fork_latched = False

        # 디버그 화면
        if self.get_parameter("debug").value:
            text = f"T:{self.truck_counter}({self.truck_latched}) F:{self.fork_counter}({self.fork_latched})"
            cv2.putText(frame, text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Webcam Debug", frame)
            cv2.waitKey(1)

    def publish_image(self, frame):
        # ROS CompressedImage 메시지 생성
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.format = "jpeg"

        # 이미지 압축
        success, buffer = cv2.imencode('.jpg', frame)
        if success:
            msg.data = buffer.tobytes()
            self.img_pub.publish(msg)

    def destroy_node(self):
        # 카메라 해제
        if self.cap is not None and self.cap.isOpened():
            self.cap.release()

        # OpenCV 창 닫기
        cv2.destroyAllWindows()

        # 부모 클래스 종료
        super().destroy_node()


def main(args=None):
    # ROS 초기화
    rclpy.init(args=args)

    node = WebcamTriggerNode()

    try:
        # 노드 실행
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # 종료 처리
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()