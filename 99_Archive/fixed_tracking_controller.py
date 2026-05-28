import math
import rclpy

from rclpy.node import Node
from geometry_msgs.msg import Twist

# [수정 추가]
# 원본은 Float32만 import 했음.
# 수정본은 follower_result, follower_cmd 같은 문자열 토픽도 받아야 하므로
# String 메시지를 추가로 import 함.
from std_msgs.msg import Float32, String
from rclpy.qos import (
    QoSProfile,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy
)

class TrackingController(Node):

    def __init__(self):
        # 노드 이름을 tracking_controller로 설정
        super().__init__('tracking_controller')

        # =====================================================
        # 파라미터 선언
        # =====================================================

        # ------------------------------------------
        # 중요한 토픽용 QoS 설정
        # RELIABLE: 가능하면 꼭 전달
        # VOLATILE: 과거 메시지는 저장 안 함
        # KEEP_LAST: 최근 메시지 몇 개만 유지
        # depth=10: 최근 10개까지 버퍼
        # ------------------------------------------
        self.important_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10
        )

        # z: 대상까지의 거리
        self.declare_parameter('z_topic', '/robot3/z')

        # yaw: 대상이 화면 중심에서 얼마나 좌우로 벗어났는지 나타내는 각도
        self.declare_parameter('yaw_topic', '/robot3/yaw')

        # [수정 추가]
        # follower가 GUI에 보내는 결과 토픽을 tracking controller도 같이 구독하도록 추가
        # 이유:
        # START 위치 도착 후 follower가 "ARRIVED_START"를 발행하면
        # tracking_controller가 그 신호를 보고 그때부터만 추종을 시작하게 하기 위함
        self.declare_parameter('result_topic', '/robot3/follower_result')

        # [수정 추가]
        # follower_cmd 토픽도 같이 구독하도록 추가
        # 이유:
        # GUI에서 GO_TO_HOME 명령이 들어오면 tracking을 멈추고
        # follower가 다시 Nav2로 HOME 복귀할 수 있도록 하기 위함
        self.declare_parameter('cmd_topic', '/leader_cmd')

        # 최종 cmd_vel 출력 토픽
        self.declare_parameter('cmd_vel_topic', '/robot3/cmd_vel')

        # 목표 거리: 이 거리 정도를 유지하며 따라가도록 설정
        self.declare_parameter('target_distance', 1)

        # 허용 오차: 너무 가까우면 멈추고, 너무 정면이면 회전 안 하도록 사용
        self.declare_parameter('distance_tolerance', 0.10)
        self.declare_parameter('yaw_tolerance', 0.08)

        # 제어 gain
        # 원본 대비 값도 수정됨:
        # 원본 kp_dist=0.5, kp_yaw=1.0 이었는데
        # 수정본은 kp_dist=0.8, kp_yaw=0.5 로 바뀜
        # -> 전진 반응은 더 적극적, 회전 반응은 조금 덜 민감하게 조정됨
        self.declare_parameter('kp_dist', 0.8)
        self.declare_parameter('kp_yaw', 0.5)

        # 최대 속도 제한
        # 원본 max_angular_speed=0.6 이었는데 수정본은 1.0
        # -> 더 빠른 회전 허용
        self.declare_parameter('max_linear_speed', 0.6)
        self.declare_parameter('max_angular_speed', 1.0)

        # yaw가 너무 크면 전진하지 않고 회전만 하도록 하는 기준값
        self.declare_parameter('turn_only_yaw_threshold', 0.20)

        # 데이터가 이 시간보다 오래되면 멈춤
        self.declare_parameter('timeout_sec', 0.5)

        # 제어 루프 주기
        self.declare_parameter('control_period', 0.1)

        # =====================================================
        # 파라미터 값 읽기
        # =====================================================
        z_topic = self.get_parameter('z_topic').value
        yaw_topic = self.get_parameter('yaw_topic').value

        # [수정 추가]
        # 위에서 선언한 result_topic, cmd_topic 값을 실제 변수로 읽음
        result_topic = self.get_parameter('result_topic').value
        cmd_topic = self.get_parameter('cmd_topic').value

        cmd_vel_topic = self.get_parameter('cmd_vel_topic').value

        self.target_distance = float(self.get_parameter('target_distance').value)
        self.distance_tolerance = float(self.get_parameter('distance_tolerance').value)
        self.yaw_tolerance = float(self.get_parameter('yaw_tolerance').value)

        self.kp_dist = float(self.get_parameter('kp_dist').value)
        self.kp_yaw = float(self.get_parameter('kp_yaw').value)

        self.max_linear_speed = float(self.get_parameter('max_linear_speed').value)
        self.max_angular_speed = float(self.get_parameter('max_angular_speed').value)

        self.turn_only_yaw_threshold = float(
            self.get_parameter('turn_only_yaw_threshold').value
        )

        self.timeout_sec = float(self.get_parameter('timeout_sec').value)
        control_period = float(self.get_parameter('control_period').value)

        # =====================================================
        # 최신 입력값 저장용 변수
        # =====================================================

        # 가장 최근 거리값
        self.latest_z = None

        # 가장 최근 yaw값
        self.latest_yaw = None

        # 최근 z가 들어온 시각
        self.last_z_time = None

        # 최근 yaw가 들어온 시각
        self.last_yaw_time = None

        # [수정 추가]
        # tracking이 현재 허용된 상태인지 저장하는 플래그
        # 기본값 False
        # -> 즉, START 도착 전에는 z/yaw가 들어와도 절대 추종하지 않음
        self.tracking_active = False

        # =====================================================
        # Subscriber
        # =====================================================

        # 거리값 구독
        self.create_subscription(Float32, z_topic, self.z_callback, 10)

        # yaw값 구독
        self.create_subscription(Float32, yaw_topic, self.yaw_callback, 10)

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

        # =====================================================
        # Publisher
        # =====================================================

        # 최종 로봇 속도 명령 발행
        self.pub_cmd_vel = self.create_publisher(Twist, cmd_vel_topic, 10)

        # =====================================================
        # Timer
        # =====================================================

        # 일정 주기마다 control_loop 실행
        self.timer = self.create_timer(control_period, self.control_loop)

        self.get_logger().info('Tracking Controller Started')

    # =====================================================
    # z 콜백
    # =====================================================
    def z_callback(self, msg: Float32):
        # 가장 최근 거리값 저장
        self.latest_z = float(msg.data)

        # 거리값이 들어온 시각 저장
        self.last_z_time = self.get_clock().now()

    # =====================================================
    # yaw 콜백
    # =====================================================
    def yaw_callback(self, msg: Float32):
        # 가장 최근 yaw값 저장
        self.latest_yaw = float(msg.data)

        # yaw값이 들어온 시각 저장
        self.last_yaw_time = self.get_clock().now()

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
    # 값 제한 함수
    # =====================================================
    def clamp(self, value, min_value, max_value):
        # 계산된 속도를 최소/최대 범위 안으로 제한
        return max(min(value, max_value), min_value)

    # =====================================================
    # 정지 명령
    # =====================================================
    def publish_stop(self):
        # 로봇을 완전히 정지시키는 cmd_vel 생성
        msg = Twist()
        msg.linear.x = 0.0
        msg.angular.z = 0.0
        self.pub_cmd_vel.publish(msg)

    # =====================================================
    # 데이터 최신 여부 체크
    # =====================================================
    def data_is_fresh(self):
        now = self.get_clock().now()

        # z 또는 yaw가 아직 한 번도 안 들어왔으면 사용 불가
        if self.last_z_time is None or self.last_yaw_time is None:
            return False

        # 마지막 데이터가 얼마나 오래됐는지 초 단위 계산
        z_age = (now - self.last_z_time).nanoseconds / 1e9
        yaw_age = (now - self.last_yaw_time).nanoseconds / 1e9

        # 너무 오래된 값이면 False
        if z_age > self.timeout_sec or yaw_age > self.timeout_sec:
            return False

        return True

    # =====================================================
    # 메인 제어 루프
    # =====================================================
    def control_loop(self):
        # [수정 추가]
        # tracking_active가 False면 무조건 정지
        # 이게 원본과의 가장 큰 차이점
        # 원본은 z/yaw만 오면 바로 움직였지만,
        # 수정본은 ARRIVED_START 신호를 받은 뒤에만 추종 가능
        if not self.tracking_active:
            # self.publish_stop()
            return

        # z/yaw가 아직 없으면 정지
        if self.latest_z is None or self.latest_yaw is None:
            # self.publish_stop()
            return

        # 데이터가 오래됐으면 정지
        if not self.data_is_fresh():
            self.get_logger().warn('Data timeout -> STOP')
            # self.publish_stop()
            return

        z = self.latest_z
        yaw = self.latest_yaw

        # z, yaw 값이 이상하면 정지
        if z <= 0.0 or math.isnan(z) or math.isnan(yaw):
            self.publish_stop()
            return

        # =====================================================
        # 오차 계산
        # =====================================================

        # 목표 거리와 현재 거리의 차이
        # 양수면 더 전진해야 함
        dist_error = z - self.target_distance

        # 화면 중심 기준 yaw 오차
        yaw_error = yaw

        # =====================================================
        # 회전 제어
        # =====================================================
        if abs(yaw_error) < self.yaw_tolerance:
            # 거의 정면이면 회전 안 함
            wz = 0.0
        else:
            # yaw 오차에 비례해서 회전속도 계산
            wz = -self.kp_yaw * yaw_error

            # 최대 회전속도 제한
            wz = self.clamp(wz, -self.max_angular_speed, self.max_angular_speed)

        # =====================================================
        # 전진 제어
        # =====================================================
        if dist_error < self.distance_tolerance:
            # 목표 거리보다 충분히 가까우면 멈춤
            vx = 0.0

        elif abs(yaw_error) > self.turn_only_yaw_threshold:
            # 방향이 많이 틀어져 있으면 전진하지 않고 회전만
            vx = 0.0

        else:
            # 거리 오차에 비례해서 전진속도 계산
            vx = self.kp_dist * dist_error

            # 최대 선속도 제한
            vx = self.clamp(vx, 0.0, self.max_linear_speed)

        # =====================================================
        # cmd_vel 발행
        # =====================================================
        cmd = Twist()
        cmd.linear.x = float(vx)
        cmd.angular.z = float(wz)

        self.pub_cmd_vel.publish(cmd)

        # 디버그 로그
        self.get_logger().info(
            f'[TRACKING] z={z:.2f} | yaw={yaw:.3f} | '
            f'err_d={dist_error:.2f} | vx={vx:.2f} | wz={wz:.2f}'
        )


# =========================================================
# main 함수
# =========================================================
def main(args=None):
    rclpy.init(args=args)
    node = TrackingController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()