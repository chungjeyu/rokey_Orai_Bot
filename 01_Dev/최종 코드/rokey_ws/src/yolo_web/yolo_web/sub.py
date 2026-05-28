import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
import cv2
from cv_bridge import CvBridge

class VerifySubNode(Node):
    def __init__(self):
        super().__init__('verify_sub_node')
        
        self.bridge = CvBridge()
        
        # 가장 최근에 받은 이미지를 저장할 변수
        self.latest_frame = None

        # 1. 감지 결과(String) 구독
        self.str_sub = self.create_subscription(
            String,
            'webcam_classed/detected_object',
            self.str_callback,
            10
        )

        # 2. 이미지(Image) 구독
        self.img_sub = self.create_subscription(
            Image,
            'webcam_classed/image_raw', 
            self.img_callback,
            10
        )

        # ✅ 중요 포인트: 0.05초마다 OpenCV 창을 계속 새로고침하는 타이머
        self.render_timer = self.create_timer(0.05, self.render_loop)

        self.get_logger().info("✅ 검증용 Subscriber 노드가 시작되었습니다. 데이터를 기다리는 중...")

    def str_callback(self, msg):
        """String 메시지가 수신될 때마다 실행"""
        self.get_logger().info(f"🚨 [감지 알림 수신] 퍼블리셔가 '{msg.data}' 객체를 감지했습니다!")

    def img_callback(self, msg):
        """Image 메시지가 수신될 때마다 실행"""
        self.get_logger().info(f"🖼️ [이미지 수신] 딱 1장 도착! 크기: {msg.width}x{msg.height}")
        
        try:
            # 수신받은 이미지를 출력하지 않고 최신 프레임 변수에 저장만 해둡니다.
            self.latest_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            
        except Exception as e:
            self.get_logger().error(f"❌ 이미지 변환 실패: {e}")

    def render_loop(self):
        """타이머가 주기적으로 실행되며 창이 멈추거나 검게 변하는 것을 방지합니다."""
        if self.latest_frame is not None:
            # 저장된 최신 프레임이 있으면 화면에 띄웁니다.
            cv2.imshow("Received Image from Publisher", self.latest_frame)
            
        # GUI 이벤트 처리를 위해 항상 실행되어야 함
        cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = VerifySubNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("프로그램을 종료합니다.")
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()