#!/usr/bin/env python3

import cv2

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image, CompressedImage
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge
from ultralytics import YOLO
from rclpy.qos import qos_profile_sensor_data


class YoloNode(Node):
    def __init__(self):
        super().__init__('yolo_node')

        # ==============================
        # Parameters
        # ==============================
        self.declare_parameter('model_path', '/home/rokey/rokey_ws/src/final_project/yolo8n_wc_ft.pt')
        # self.declare_parameter('rgb_topic', '/robot3/oakd/rgb/preview/image_raw')
        self.declare_parameter('rgb_topic', '/robot3/oakd/rgb/image_raw/compressed')
        self.declare_parameter('detection_topic', '/robot3/detection')
        self.declare_parameter('target_class_name', ['fork', 'truck'])
        self.declare_parameter('conf_threshold', 0.35)
        self.declare_parameter('min_box_area_ratio', 0.01)   # bbox가 화면의 1% 미만이면 무시
        self.declare_parameter('timer_period', 0.2)
        self.declare_parameter('show_debug_image', True)

        model_path = self.get_parameter('model_path').value
        rgb_topic = self.get_parameter('rgb_topic').value
        detection_topic = self.get_parameter('detection_topic').value
        self.target_class_name = self.get_parameter('target_class_name').value
        self.conf_threshold = float(self.get_parameter('conf_threshold').value)
        self.min_box_area_ratio = float(self.get_parameter('min_box_area_ratio').value)
        timer_period = float(self.get_parameter('timer_period').value)
        self.show_debug_image = bool(self.get_parameter('show_debug_image').value)

        # ==============================
        # Objects
        # ==============================
        self.bridge = CvBridge()
        self.model = YOLO(model_path)

        # 최신 RGB 프레임
        self.rgb_image = None
        self.camera_frame = None
        self.stamp = None

        self.last_pub_u = None
        self.last_pub_v = None

        # ==============================
        # Subscriber
        # ==============================
        self.sub_rgb = self.create_subscription(
            CompressedImage,
            rgb_topic,
            self.rgb_callback,
            qos_profile_sensor_data
        )

        # ==============================
        # Publisher
        # ==============================
        self.pub_detection = self.create_publisher(
            PointStamped,
            detection_topic,
            qos_profile_sensor_data
        )

        # ==============================
        # Timer
        # ==============================
        self.timer = self.create_timer(timer_period, self.process_frame)

        self.get_logger().info('YOLO Node Initialized')
            

    def rgb_callback(self, msg: CompressedImage):
        try:
            self.rgb_image = self.bridge.compressed_imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.camera_frame = 'oakd_rgb_camera_optical_frame'   # 필요시 실제 프레임명으로 수정
            self.stamp = self.get_clock().now().to_msg()          # compressed에는 일반 Image처럼 header가 없을 수 있음

            # h, w = self.rgb_image.shape[:2]
            # self.get_logger().info(f'rgb_size, w: {w}, h: {h}')

        except Exception as e:
            self.get_logger().error(f'CV Bridge Error: {e}')

    def process_frame(self):
        # self.get_logger().info('processing..')
        if self.rgb_image is None or self.stamp is None:
            return

        try:
            image = self.rgb_image.copy()
        except Exception:
            return

        h, w = image.shape[:2]
        img_area = float(h * w)

        # YOLO inference
        results = self.model.predict(
            image,
            conf=self.conf_threshold,
            verbose=False
        )

        if len(results) == 0:
            self.show_image(image)
            return

        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            self.show_image(image)
            return

        best_box = None
        best_conf = -1.0

        for box in r.boxes:
            cls = int(box.cls[0]) if box.cls is not None else -1
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            class_name = self.model.names[cls] if cls in self.model.names else str(cls)

            if class_name not in self.target_class_name:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bw = max(0, x2 - x1)
            bh = max(0, y2 - y1)
            area_ratio = (bw * bh) / img_area if img_area > 0 else 0.0

            if area_ratio < self.min_box_area_ratio:
                continue

            if conf > best_conf:
                best_conf = conf
                best_box = box

        if best_box is None:
            self.show_image(image)
            return

        x1, y1, x2, y2 = map(int, best_box.xyxy[0])
        cls = int(best_box.cls[0]) if best_box.cls is not None else 0
        conf = float(best_box.conf[0]) if best_box.conf is not None else 0.0
        class_name = self.model.names[cls]

        u = int((x1 + x2) / 2)
        v = int((y1 + y2) / 2)

        # 시각화
        label = f"{class_name} {conf:.2f}"
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.circle(image, (u, v), 5, (255, 0, 0), -1)
        cv2.putText(
            image,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )

        msg = PointStamped()
        msg.header.stamp = self.stamp
        msg.header.frame_id = self.camera_frame
        msg.point.x = float(u)
        msg.point.y = float(v)
        msg.point.z = float(conf)

        self.pub_detection.publish(msg)
        self.get_logger().info(f'image_raw/compressed size, w: {w}, h: {h}')

        self.last_pub_u = u
        self.last_pub_v = v

        self.show_image(image)

    def show_image(self, image):
        if not self.show_debug_image:
            return
        cv2.imshow("YOLOv8 Detection", image)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    node = YoloNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()