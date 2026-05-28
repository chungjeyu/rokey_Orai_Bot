#!/usr/bin/env python3

import cv2

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge

from ultralytics import YOLO
from rclpy.qos import qos_profile_sensor_data


class YoloNode(Node):
    def __init__(self):
        super().__init__('yolo_node')

        # ===== 기본 객체 =====
        self.bridge = CvBridge()
        self.model = YOLO('/home/rokey/rokey_ws/src/final_project/yolo8n_wc_ft.pt')

        # ===== 최신 RGB 프레임 정보 =====
        self.rgb_image = None
        self.camera_frame = None
        self.stamp = None

        # ===== Subscriber =====
        self.sub_rgb = self.create_subscription(
            Image,
            '/robot4/oakd/rgb/preview/image_raw',
            self.rgb_callback,
            qos_profile_sensor_data
        )

        # ===== Publisher =====
        # depth 노드가 받을 중심점(u, v)
        self.pub_detection = self.create_publisher(
            PointStamped,
            '/robot4/detection',
            qos_profile_sensor_data
        )

        # ===== Timer =====
        # 너무 빠르면 YOLO 추론이 버거울 수 있으니 0.2~0.3초 정도부터 시작
        self.timer = self.create_timer(0.2, self.process_frame)

        self.get_logger().info('YOLO Node Initialized')

    # =========================================================
    # RGB CALLBACK
    # =========================================================
    def rgb_callback(self, msg: Image):
        try:
            self.rgb_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
            self.camera_frame = msg.header.frame_id
            self.stamp = msg.header.stamp

        except Exception as e:
            self.get_logger().error(f'CV Bridge Error: {e}')

    # =========================================================
    # YOLO TIMER CALLBACK
    # =========================================================
    def process_frame(self):
        if self.rgb_image is None or self.stamp is None:
            return

        try:
            image = self.rgb_image.copy()
        except Exception:
            return

        # YOLO 추론
        results = self.model.predict(
            image,
            conf=0.3,
            verbose=False
        )

        # if len(results) == 0:
        #     cv2.imshow("YOLOv8 Detection", image)
        #     cv2.waitKey(1)
        #     return

        r = results[0]

        # if r.boxes is None or len(r.boxes) == 0:
        #     cv2.imshow("YOLOv8 Detection", image)
        #     cv2.waitKey(1)
        #     return

        # =====================================================
        # 가장 confidence 높은 박스 하나만 선택
        # =====================================================
        best_box = None
        best_conf = -1.0

        for box in r.boxes:
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            if conf > best_conf:
                best_conf = conf
                best_box = box

        if best_box is None:
            cv2.imshow("YOLOv8 Detection", image)
            cv2.waitKey(1)
            return

        # 박스 정보 추출
        x1, y1, x2, y2 = map(int, best_box.xyxy[0])
        cls = int(best_box.cls[0]) if best_box.cls is not None else 0
        conf = float(best_box.conf[0]) if best_box.conf is not None else 0.0
        class_name = self.model.names[cls]

        # 중심점 계산
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

        # =====================================================
        # PointStamped publish
        # depth 노드가 아래 형태로 받음
        # msg.point.x = u
        # msg.point.y = v
        # msg.header.frame_id = RGB camera frame
        # msg.header.stamp = RGB image stamp
        # =====================================================
        msg = PointStamped()
        msg.header.stamp = self.stamp
        msg.header.frame_id = self.camera_frame
        msg.point.x = float(u)
        msg.point.y = float(v)
        msg.point.z = 0.0

        self.pub_detection.publish(msg)

        self.get_logger().info(
            f'Published detection center: u={u}, v={v}, '
            f'class={class_name}, conf={conf:.2f}'
        )

        # 화면 출력
        cv2.imshow("YOLOv8 Detection", image)
        cv2.waitKey(1)


# =========================================================
# MAIN
# =========================================================
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