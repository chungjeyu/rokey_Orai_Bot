import rclpy
from rclpy.node import Node
from std_msgs.msg import String

class MinimalSubscriber(Node):
    def __init__(self):
        super().__init__('pc_test_subscriber')
        # 퍼블리셔와 동일한 'multi_pc_topic' 구독
        self.subscription = self.create_subscription(
            String,
            'multi_pc_topic',
            self.listener_callback,
            10)
        self.subscription  # unused variable 경고 방지

    def listener_callback(self, msg):
        self.get_logger().info(f'Received: "{msg.data}"')

def main(args=None):
    rclpy.init(args=args)
    minimal_subscriber = MinimalSubscriber()
    
    try:
        rclpy.spin(minimal_subscriber)
    except KeyboardInterrupt:
        pass
    finally:
        minimal_subscriber.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()