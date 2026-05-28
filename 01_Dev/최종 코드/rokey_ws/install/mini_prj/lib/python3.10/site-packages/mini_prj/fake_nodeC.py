import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool

class FakeNodeC(Node):
    def __init__(self):
        super().__init__('fake_node_c')
        self.create_service(
            SetBool,
            '/robot8/node_c_enable',
            self.cb
        )

    def cb(self, req, res):
        self.get_logger().info(f"Request: {req.data}")
        res.success = True
        res.message = "Fake NodeC Started"
        return res

rclpy.init()
node = FakeNodeC()
rclpy.spin(node)