from queue import Queue
import cv2

import rclpy
from rclpy.node import Node
# from std_msgs.msg import Float32
from sensor_msgs.msg import Image
from geometry_msgs.msg import PointStamped
from cv_bridge import CvBridge

from ultralytics import YOLO

from my_interfaces.msg import Detection
from rclpy.qos import qos_profile_sensor_data


class YoloNode(Node):
    def __init__(self):
        # 노드 초기화
        super().__init__('yolo_node')

        self.bridge = CvBridge()
        self.model = YOLO('/home/rokey/rokey_ws/src/miniproject/tb_best4.pt')

        self.should_shutdown = False

        # 최신 이미지 및 메타데이터 저장
        self.rgb_image = None
        self.camera_frame = None
        self.stamp = None

        # (선택) 최신 프레임 버퍼
        self.image_queue = Queue(maxsize=1)

        # RGB 이미지 구독
        self.create_subscription(
            Image,
            '/robot8/oakd/rgb/preview/image_raw',
            self.rgb_callback,
            10
        )

        # detection 결과 publish
        self.pub_to_node_c = self.create_publisher(
            PointStamped,
            '/robot8/detection',
            qos_profile_sensor_data
        )

        self.pub_to_node_a = self.create_publisher(
            Detection,
            '/robot8/confidence',
            qos_profile_sensor_data
        )

        # 주기적으로 YOLO 실행 (timer callback)
        self.timer = self.create_timer(0.3, self.process_frame)

        self.get_logger().info('YOLO Node Initialized')

    # =========================================================
    # IMAGE CALLBACK
    # =========================================================
    def rgb_callback(self, msg):
        """이미지 수신 → OpenCV 변환 후 저장"""
        # self.get_logger().info('RGB 이미지 수신됨')

        try:
            self.rgb_image = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

            h, w = self.rgb_image.shape[:2]
            self.get_logger().info(f"RGB 실제 해상도: {w} x {h}")
            # queue는 최신 프레임 유지용 (optional)
            if not self.image_queue.full():
                self.image_queue.put(self.rgb_image)
            else:
                self.image_queue.get()
                self.image_queue.put(self.rgb_image)

            self.camera_frame = msg.header.frame_id
            self.stamp = msg.header.stamp

        except Exception as e:
            self.get_logger().error(f'CV Bridge Error: {e}')

    # =========================================================
    # YOLO TIMER CALLBACK
    # =========================================================
    def process_frame(self):
        """저장된 이미지로 YOLO 수행 후 detection 결과 표시"""

        if self.rgb_image is None or self.stamp is None:
            return

        try:
            # 이미지 복사 (thread 안전)
            image = self.rgb_image.copy()
        except:
            return

        # =====================================================
        # YOLO inference
        # =====================================================
        results = self.model.predict(image, conf=0.7)

        if len(results) == 0:
            return

        r = results[0]

        if r.boxes is None:
            cv2.imshow("YOLOv8 Detection", image)
            cv2.waitKey(1)
            return

        # =====================================================
        # detection loop
        # =====================================================
        for box in r.boxes:

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            cls = int(box.cls[0]) if box.cls is not None else 0
            conf = float(box.conf[0]) if box.conf is not None else 0.0

            label = f"{self.model.names[cls]} {conf:.2f}"

            # bounding box visualization
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(
                image,
                label,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

            # =================================================
            # publish (center point + confidence)
            # =================================================
            u = int((x1 + x2) / 2)
            v = int((y1 + y2) / 2)

            msg_to_node_a = Detection()
            msg_to_node_a.confidence = conf
            msg_to_node_a.label = self.model.names[cls]

            self.pub_to_node_a.publish(msg_to_node_a)

            msg_to_node_c = PointStamped()
            msg_to_node_c.header.stamp = self.stamp
            msg_to_node_c.header.frame_id = self.camera_frame
            msg_to_node_c.point.x = float(u)
            msg_to_node_c.point.y = float(v)
            msg_to_node_c.point.z = 0.0

            self.pub_to_node_c.publish(msg_to_node_c)

        # =====================================================
        # display
        # =====================================================
        cv2.imshow("YOLOv8 Detection", image)
        cv2.waitKey(1)


# =========================================================
# MAIN
# =========================================================
def main():
    rclpy.init()
    node = YoloNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
