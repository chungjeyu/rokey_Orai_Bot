import cv2
import math
import numpy as np
import rclpy

from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage, CameraInfo
from std_msgs.msg import Float32, String
from cv_bridge import CvBridge
from ultralytics import YOLO
from rclpy.qos import (
    qos_profile_sensor_data,
    QoSProfile,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy
)

from rclpy.executors import MultiThreadedExecutor



class YoloDepth(Node):
    def __init__(self):
        # -------------------------------------------------
        # 노드 이름 설정
        # -------------------------------------------------
        super().__init__('yolo_depth')

        self.important_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10
        )

        # -------------------------------------------------
        # 파라미터 선언
        # 필요시 launch 파일이나 ros2 run --ros-args 로 변경 가능
        # -------------------------------------------------
        self.declare_parameter('depth_topic', 'oakd/stereo/image_raw')
        self.declare_parameter('rgb_topic', 'oakd/rgb/image_raw/compressed')
        self.declare_parameter('camera_info_topic', 'oakd/stereo/camera_info')
        self.declare_parameter('model_path', '/home/rokey/rokey_ws/src/ch_final_project/amr_yolon_26424.pt')
        self.declare_parameter('target_class_name', ['fork', 'truck'])
        self.declare_parameter('conf_threshold', 0.8)
        self.declare_parameter('min_box_area_ratio', 0.01)
        self.declare_parameter('timer_period', 0.1)
        self.declare_parameter('show_debug_image', False)

        # [수정 추가]
        # follower가 GUI에 보내는 결과 토픽을 tracking controller도 같이 구독하도록 추가
        # 이유:
        # START 위치 도착 후 follower가 "ARRIVED_START"를 발행하면
        # tracking_controller가 그 신호를 보고 그때부터만 추종을 시작하게 하기 위함
        self.declare_parameter('result_topic', 'follower_result')

        # [수정 추가]
        # follower_cmd 토픽도 같이 구독하도록 추가
        # 이유:
        # GUI에서 GO_TO_HOME 명령이 들어오면 tracking을 멈추고
        # follower가 다시 Nav2로 HOME 복귀할 수 있도록 하기 위함
        self.declare_parameter('cmd_topic', '/leader_cmd')

        # -------------------------------------------------
        # 파라미터 읽기
        # -------------------------------------------------
        rgb_topic = self.get_parameter('rgb_topic').value
        depth_topic = self.get_parameter('depth_topic').value
        camera_info_topic = self.get_parameter('camera_info_topic').value
        model_path = self.get_parameter('model_path').value

        # [수정 추가]
        # 위에서 선언한 result_topic, cmd_topic 값을 실제 변수로 읽음
        result_topic = self.get_parameter('result_topic').value
        cmd_topic = self.get_parameter('cmd_topic').value

        self.target_class_name = self.get_parameter('target_class_name').value
        self.conf_threshold = float(self.get_parameter('conf_threshold').value)
        self.min_box_area_ratio = float(self.get_parameter('min_box_area_ratio').value)
        self.show_debug_image = bool(self.get_parameter('show_debug_image').value)
        timer_period = float(self.get_parameter('timer_period').value)

        # -------------------------------------------------
        # 객체 준비
        # CvBridge : ROS 이미지 ↔ OpenCV 이미지 변환
        # YOLO     : 객체 검출 모델
        # -------------------------------------------------
        self.bridge = CvBridge()
        self.model = YOLO(model_path).to('cuda')

        # -------------------------------------------------
        # 최신 데이터 저장용 변수
        # rgb_image   : 최신 RGB 영상
        # depth_image : 최신 depth 영상
        # K           : CameraInfo에서 받은 내부파라미터 행렬
        # -------------------------------------------------
        self.rgb_image = None
        self.depth_image = None
        self.depth_w = None
        self.depth_h = None
        self.K = None
        self.last_log_time = self.get_clock().now()
        self.tracking_active = False
        # self.tracking_active = True   # 기능 테스트 시, True 사용, 그 외엔 False 고정

        # -------------------------------------------------
        # depth 허용 범위
        # 너무 작은 값 / 너무 큰 값은 무시
        # -------------------------------------------------
        self.min_depth = 0.05   # meter
        self.max_depth = 10.0  # meter

        # -------------------------------------------------
        # Subscriber 생성
        # 1) RGB compressed image
        # 2) Depth raw image
        # 3) CameraInfo
        # -------------------------------------------------
        self.create_subscription(
            CompressedImage,
            rgb_topic,
            self.rgb_callback,
            qos_profile_sensor_data
        )

        self.create_subscription(
            Image,
            depth_topic,
            self.depth_callback,
            qos_profile_sensor_data
        )

        self.create_subscription(
            CameraInfo,
            camera_info_topic,
            self.camera_info_callback,
            qos_profile_sensor_data
        )

        # [수정 추가]
        # follower_result 구독
        # follower가 START 위치 도착 후 ARRIVED_START를 보내면
        # 이 콜백에서 tracking_active를 True로 바꿔서 추종 시작
        self.create_subscription(String, result_topic, self.result_callback, self.important_qos)

        # [수정 추가]
        # follower_cmd 구독
        # GUI에서 GO_TO_HOME 명령이 들어오면
        # 이 콜백에서 tracking_active를 False로 바꿔 추종 중지
        self.create_subscription(String, cmd_topic, self.cmd_callback, self.important_qos)

        # -------------------------------------------------
        # Publisher 생성
        # z   : 객체까지 거리 [m]
        # yaw : 객체 방향 오차 [rad]
        # -------------------------------------------------
        self.pub_z = self.create_publisher(Float32, 'z', 10)
        self.pub_yaw = self.create_publisher(Float32, 'yaw', 10)

        # -------------------------------------------------
        # Timer
        # 주기적으로 process_frame()을 호출하여 검출 수행
        # -------------------------------------------------
        self.timer = self.create_timer(timer_period, self.process_frame)

        
        self.get_logger().info('YOLO Node Initialized')
        self.get_logger().info('tracking off')

    # =====================================================
    # RGB 콜백
    # CompressedImage -> OpenCV BGR 이미지 변환
    # =====================================================
    def rgb_callback(self, msg: CompressedImage):
        try:
            # self.get_logger().info('rgb 들어오는 중')
            self.rgb_image = self.bridge.compressed_imgmsg_to_cv2(
                msg,
                desired_encoding='bgr8'
            )
        except Exception as e:
            self.get_logger().error(f'RGB callback error: {e}')

    # =====================================================
    # Depth 콜백
    # ROS depth image -> OpenCV depth image 변환
    # 보통 uint16(mm) 또는 float(m) 형태로 들어온다
    # =====================================================
    def depth_callback(self, msg: Image):
        try:
            # self.get_logger().info('depth 들어오는 중')
            self.depth_image = self.bridge.imgmsg_to_cv2(
                msg,
                desired_encoding='passthrough'
            )
            # depth 영상 크기 저장
            self.depth_h, self.depth_w = self.depth_image.shape[:2]

        except Exception as e:
            self.get_logger().error(f'Depth callback error: {e}')

    # =====================================================
    # CameraInfo 콜백
    # 카메라 내부파라미터 K 저장
    # K = [[fx,  0, cx],
    #      [ 0, fy, cy],
    #      [ 0,  0,  1]]
    # =====================================================
    def camera_info_callback(self, msg: CameraInfo):
        try:
            self.K = np.array(msg.k, dtype=np.float64).reshape(3, 3)
        except Exception as e:
            self.get_logger().warn(f'camera_info_callback failed: {e}')


    # =====================================================
    # [수정 추가] result 콜백
    # =====================================================
    def result_callback(self, msg: String):
        # follower_result 토픽에서 문자열을 받아 대문자로 정리
        result = msg.data.strip().upper()

        # [수정 추가]
        # follower가 START 위치에 도착했을 때만 tracking 시작
        # 즉, 이 신호를 받기 전에는 control_loop가 절대 움직이지 않음
        if result == "ARRIVED_START":
            self.tracking_active = True
            self.get_logger().info("ARRIVED_START 수신 -> tracking 시작")

    # =====================================================
    # [수정 추가] cmd 콜백
    # =====================================================
    def cmd_callback(self, msg: String):
        # follower_cmd 토픽에서 명령 문자열 수신
        cmd = msg.data.strip().upper()

        # [수정 추가]
        # HOME 복귀 명령이 들어오면 tracking 중지
        # 이후 follower는 Nav2를 사용해서 HOME으로 돌아갈 수 있음
        if cmd == "GO_TO_HOME":
            self.tracking_active = False
            self.publish_stop()
            self.get_logger().info("GO_TO_HOME 수신 -> tracking 정지")

    # =====================================================
    # 중심점 주변 depth 추출
    # 단일 픽셀만 쓰지 않고 5x5 window에서 유효값만 모아
    # percentile 값으로 대표 depth를 얻음
    # =====================================================
    def get_depth(self, u, v):
        # depth 영상이 아직 없으면 계산 불가
        if self.depth_image is None or self.depth_w is None or self.depth_h is None:
            return None

        # 중심 주변 5x5 window 범위 계산
        r = 2
        u0 = max(0, u - r)
        u1 = min(self.depth_w, u + r + 1)
        v0 = max(0, v - r)
        v1 = min(self.depth_h, v + r + 1)

        # window 잘라내기
        region = self.depth_image[v0:v1, u0:u1]

        # 유효값만 선택
        # - finite
        # - 0보다 큰 값
        valid = region[np.isfinite(region) & (region > 0)]

        if valid.size == 0:
            return None

        # 가까운 쪽 값을 좀 더 믿기 위해 20 percentile 사용
        z = float(np.percentile(valid, 20))

        # depth가 uint16이면 보통 mm 단위이므로 m로 변환
        if self.depth_image.dtype == np.uint16:
            z /= 1000.0

        # 너무 작거나 너무 큰 값은 무시
        if z < self.min_depth or z > self.max_depth:
            return None

        return z

    # =====================================================
    # 픽셀 u로부터 yaw 계산
    # yaw = atan2(u - cx, fx)
    # 오른쪽이면 양수, 왼쪽이면 음수
    # =====================================================
    def get_yaw_from_pixel(self, u):
        if self.K is None:
            return None

        fx = float(self.K[0, 0])
        cx = float(self.K[0, 2])

        # 혹시라도 fx가 이상하면 계산하지 않음
        if fx <= 0.0:
            return None

        yaw = math.atan2((u - cx), fx)
        return yaw

    # =====================================================
    # bbox 위에 여러 줄 텍스트를 그리는 함수
    # class, conf, z, yaw, (u,v) 표시
    # =====================================================
    def draw_label_block(self, image, x1, y1, lines):
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.55
        thickness = 2
        line_gap = 6

        # 각 줄 텍스트 크기 계산
        sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
        text_width = max(w for w, h in sizes) if sizes else 0
        text_height = sum(h for w, h in sizes) + line_gap * (len(lines) - 1)

        # 검은 배경 박스 위치 계산
        pad = 6
        box_x1 = x1
        box_y2 = max(y1 - 8, 0)
        box_y1 = max(box_y2 - text_height - 2 * pad, 0)
        box_x2 = min(box_x1 + text_width + 2 * pad, image.shape[1] - 1)

        # 배경 박스
        cv2.rectangle(image, (box_x1, box_y1), (box_x2, box_y2), (0, 0, 0), -1)

        # 텍스트 여러 줄 그리기
        y = box_y1 + pad
        for line, (tw, th) in zip(lines, sizes):
            y += th
            cv2.putText(
                image,
                line,
                (box_x1 + pad, y),
                font,
                font_scale,
                (0, 255, 0),
                thickness
            )
            y += line_gap

    # =====================================================
    # 디버그용 화면 출력
    # show_debug_image=False면 창을 띄우지 않음
    # =====================================================
    def show_image(self, image):
        if not self.show_debug_image:
            return

        cv2.imshow("YOLO Detection UI", image)
        cv2.waitKey(1)

    # =====================================================
    # 메인 처리 함수
    # 1) RGB 영상에서 YOLO 검출
    # 2) 대상 클래스 중 최고 conf 박스 선택
    # 3) 중심점 (u,v) 계산
    # 4) depth -> z 계산
    # 5) pixel -> yaw 계산
    # 6) z, yaw 퍼블리시
    # 7) 화면에 bbox + 정보 표시
    # =====================================================
    def process_frame(self):
        # [수정 추가]
        # tracking_active가 False면 무조건 정지
        # 이게 원본과의 가장 큰 차이점
        # 원본은 z/yaw만 오면 바로 움직였지만,
        # 수정본은 ARRIVED_START 신호를 받은 뒤에만 추종 가능
        # now = self.get_clock().now()
        # dt = (now - self.last_log_time).nanoseconds / 1e9

        # if dt > 1.0:
        #     self.get_logger().info(
        #         self.get_logger().info(self.tracking_active)
        #     )
        #     self.last_log_time = now

        if not self.tracking_active:
            return

        # 필요한 데이터가 아직 안 들어왔으면 실행하지 않음
        if self.rgb_image is None:
            return
        if self.depth_image is None or self.depth_w is None or self.depth_h is None:
            return
        if self.K is None:
            return

        # 영상 복사
        try:
            image = self.rgb_image.copy()
        except Exception:
            return

        h, w = image.shape[:2]
        img_area = float(h * w)

        # -------------------------------------------------
        # YOLO 추론
        # -------------------------------------------------
        results = self.model.predict(
            image,
            conf=self.conf_threshold,
            verbose=False
        )

        # 검출 결과가 없으면 그냥 화면만 띄움
        if len(results) == 0:
            self.show_image(image)
            return

        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            self.show_image(image)
            return

        # -------------------------------------------------
        # 대상 클래스 중 가장 confidence 높은 박스 선택
        # -------------------------------------------------
        best_box = None
        best_conf = -1.0

        for box in r.boxes:
            cls = int(box.cls[0]) if box.cls is not None else -1
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            class_name = self.model.names[cls] if cls in self.model.names else str(cls)

            # 목표 클래스가 아니면 무시
            if class_name not in self.target_class_name:
                continue

            # bbox 크기 계산
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bw = max(0, x2 - x1)
            bh = max(0, y2 - y1)
            area_ratio = (bw * bh) / img_area if img_area > 0 else 0.0

            # 너무 작은 bbox는 무시
            if area_ratio < self.min_box_area_ratio:
                continue

            # confidence 가장 높은 박스 선택
            if conf > best_conf:
                best_conf = conf
                best_box = box

        # 목표 객체가 없으면 화면만 출력
        if best_box is None:
            self.show_image(image)
            return

        # -------------------------------------------------
        # 선택된 박스의 정보 추출
        # -------------------------------------------------
        x1, y1, x2, y2 = map(int, best_box.xyxy[0])
        cls = int(best_box.cls[0]) if best_box.cls is not None else 0
        conf = float(best_box.conf[0]) if best_box.conf is not None else 0.0
        class_name = self.model.names[cls]

        # bbox 중심점
        u = int((x1 + x2) / 2)
        v = int((y1 + y2) / 2)

        # 중심점이 depth 영상 범위를 벗어나면 중단
        if not (0 <= u < self.depth_w and 0 <= v < self.depth_h):
            self.get_logger().warn(f'uv out of range: ({u}, {v})')
            self.show_image(image)
            return

        # -------------------------------------------------
        # 거리 z 계산
        # -------------------------------------------------
        z = self.get_depth(u, v)
        if z is None:
            self.show_image(image)
            return

        # -------------------------------------------------
        # yaw 계산
        # -------------------------------------------------
        yaw = self.get_yaw_from_pixel(u)
        if yaw is None:
            self.show_image(image)
            return

        # -------------------------------------------------
        # 거리 z 퍼블리시
        # -------------------------------------------------
        msg_z = Float32()
        msg_z.data = float(z)
        self.pub_z.publish(msg_z)

        # -------------------------------------------------
        # yaw 퍼블리시
        # -------------------------------------------------
        msg_yaw = Float32()
        msg_yaw.data = float(yaw)
        self.pub_yaw.publish(msg_yaw)

        # -------------------------------------------------
        # 시각화
        # - bbox
        # - 중심점
        # - 텍스트 정보
        # -------------------------------------------------
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.circle(image, (u, v), 5, (255, 0, 0), -1)

        lines = [
            f"class: {class_name}",
            f"conf : {conf:.2f}",
            f"dist : {z:.2f} m",
            f"yaw  : {yaw:.3f} rad ({math.degrees(yaw):.1f} deg)",
            f"u, v : ({u}, {v})"
        ]
        self.draw_label_block(image, x1, y1, lines)

        # -------------------------------------------------
        # 로그 출력
        # -------------------------------------------------
        now = self.get_clock().now()
        dt = (now - self.last_log_time).nanoseconds / 1e9

        if dt > 1.0:
            self.get_logger().info(
                f"{class_name} | conf={conf:.2f} | z={z:.2f} m | yaw={yaw:.3f} rad | uv=({u},{v})"
            )
            self.last_log_time = now

        # 화면 표시
        self.show_image(image)

# =========================================================
# main 함수
# =========================================================
def main(args=None):

    rclpy.init(args=args)
    node = YoloDepth()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try: 
        executor.spin()
    except KeyboardInterrupt: 
        pass
    finally: 
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()
if __name__ == '__main__':
    main()