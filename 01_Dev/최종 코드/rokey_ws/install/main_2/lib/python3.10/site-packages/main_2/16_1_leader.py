import math
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor 
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup 
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from std_msgs.msg import String, Bool # 🔥 Bool 추가 (이벤트 수신용)

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')
        
        self.cmd_cb_group = MutuallyExclusiveCallbackGroup()   
        self.pose_cb_group = MutuallyExclusiveCallbackGroup()  
        self.timer_cb_group = MutuallyExclusiveCallbackGroup() 
        self.event_cb_group = MutuallyExclusiveCallbackGroup() # 🔥 이벤트 수신용 콜백 그룹 추가

        # 목적지 데이터 테이블 (생략... 기존과 동일)
        self.targets = { ... }

        # Follower 관련 파라미터 (생략... 기존과 동일)
        self.max_f_dist = 2.0
        self.resume_f_dist = 1.5
        self.leader_pose = None
        self.follower_pose = None
        self.is_waiting_for_follower = False 
        self.current_goal_pose = None        

        # 상태 변수
        self.current_state = None  
        self.goal_active = False
        self.current_goal_cmd = None 
        self.is_threatened = False   
        
        # 🔥 외부 이벤트 정지 상태를 관리하는 플래그 추가 🔥
        self.is_event_paused = False 

        # 통신 설정
        self.state_pub = self.create_publisher(String, 'leader_state', 10)
        self.result_pub = self.create_publisher(String, 'leader_result', 10) 

        self.create_subscription(String, 'leader_cmd', self.cmd_callback, 10, callback_group=self.cmd_cb_group)
        self.create_subscription(PoseWithCovarianceStamped, 'amcl_pose', self.leader_pose_callback, 10, callback_group=self.pose_cb_group)
        self.create_subscription(PoseWithCovarianceStamped, '/robot3/amcl_pose', self.follower_pose_callback, 10, callback_group=self.pose_cb_group)

        # =========================================================
        # 🔥 외부 이벤트 토픽 구독 (예: /external_pause_event)
        # =========================================================
        self.create_subscription(
            Bool, 
            '/external_pause_event', 
            self.external_event_callback, 
            10, 
            callback_group=self.event_cb_group
        )

        # Nav2 초기화
        self.navigator = TurtleBot4Navigator()
        self.create_timer(0.1, self.monitor_nav_status, callback_group=self.timer_cb_group)
        self.set_state("Wait")

    # =========================================================
    # 🔥 임의의 이벤트 수신 콜백 함수 🔥
    # =========================================================
    def external_event_callback(self, msg):
        pause_requested = msg.data # True: 정지 요청, False: 재출발 요청

        # 1. 정지 이벤트 발생
        if pause_requested and not self.is_event_paused:
            if self.goal_active: # 이동 중일 때만 세움
                self.get_logger().warn("🚨 [이벤트 발생] 외부 정지 신호 수신! 로봇을 즉시 정지합니다.")
                self.navigator.cancelTask() # Nav2 주행 취소
                self.is_event_paused = True
                self.set_state("Event_Paused") 

        # 2. 정지 이벤트 해제 (재출발)
        elif not pause_requested and self.is_event_paused:
            self.get_logger().info("✅ [이벤트 해제] 정지 신호 해제! 저장된 목적지로 재출발합니다.")
            self.is_event_paused = False
            
            # 저장해두었던 목적지로 다시 goToPose 명령을 내림
            if self.current_goal_pose is not None:
                self.navigator.goToPose(self.current_goal_pose)
                self.set_state("goal_planning") # 상태 복구

    # 기존 콜백 및 보조 함수들...
    def leader_pose_callback(self, msg): pass # (기존과 동일)
    def follower_pose_callback(self, msg): pass # (기존과 동일)
    def set_state(self, new_state): pass # (기존과 동일)
    def get_follower_distance(self): pass # (기존과 동일)

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        # 🔥 이벤트로 멈춰있을 때는 새로운 명령을 무시 (선택사항)
        if self.is_threatened or self.goal_active or self.is_event_paused:
            self.get_logger().warn("⚠️ 현재 주행 중이거나 이벤트 정지 상태이므로 명령을 무시합니다.")
            return 
        # (나머지 기존 START, GO_TO 로직 동일)

    def process_movement(self, cmd):
        # (기존과 동일하게 목적지를 세팅하고 goToPose 실행)
        target = self.targets[cmd]
        self.current_goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(self.current_goal_pose)
        self.goal_active = True
        self.current_goal_cmd = cmd
        self.is_waiting_for_follower = False
        if cmd not in ["START", "GO_TO_HOME"]:
            self.set_state("goal_planning") 

    def monitor_nav_status(self):
        if not self.goal_active: return

        # 🔥 이벤트로 정지된 상태라면 아래의 도착 체크나 Follower 체크를 무시함
        if self.is_event_paused:
            return

        # (기존 Follower 거리 체크 로직)
        
        # (기존 Nav2 완료 체크 로직)
        if self.navigator.isTaskComplete():
            result = self.navigator.getResult()
            if result == TaskResult.SUCCEEDED:
                # (기존 SUCCEEDED 처리 로직)
                pass

            elif result == TaskResult.CANCELED:
                # 🔥 외부 이벤트나 Follower 대기로 인해 cancelTask()가 호출된 경우
                # goal_active를 False로 바꾸지 않고 유지합니다. (나중에 재출발해야 하므로)
                if self.is_waiting_for_follower or self.is_event_paused:
                    pass 
                elif self.is_threatened:
                    self.goal_active = False
                else:
                    self.goal_active = False

# (main 함수 기존과 동일)
def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    
    # =========================================================
    # 🔥 MultiThreadedExecutor 적용 부분 🔥
    # 스레드 개수(num_threads)를 지정하지 않으면 시스템 CPU 코어 수에 맞춰 자동 생성됩니다.
    # =========================================================
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    
    try: 
        executor.spin() # rclpy.spin(node) 대신 executor.spin() 사용
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()