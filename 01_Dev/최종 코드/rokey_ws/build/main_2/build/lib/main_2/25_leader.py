#18_leader/usr/bin/env python3

import math
import sys
import os      # 프로세스 강제 종료용
import time    # 퍼블리시 지연 대기용
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup

# 🔥 [String 타입 비상 정지 변경] Bool 임포트 제거, String만 사용
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
from irobot_create_msgs.msg import AudioNoteVector, AudioNote
from builtin_interfaces.msg import Duration

# 🔥 [배터리 중계 추가] BatteryState 메시지 임포트
from sensor_msgs.msg import BatteryState

# QoS 
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy
# from rclpy.qos import qos_profile_sensor_data

from turtlebot4_navigation.turtlebot4_navigator import TurtleBot4Navigator, TaskResult

class LeaderNode(Node):
    def __init__(self):
        super().__init__('leader_node')
        
        self.important_qos = QoSProfile(
          reliability=QoSReliabilityPolicy.RELIABLE,
          durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
          history=QoSHistoryPolicy.KEEP_LAST,
          depth=10
        )

        # =========================================================
        # 콜백 그룹(Callback Group) 설정
        # =========================================================
        self.cmd_cb_group = MutuallyExclusiveCallbackGroup()   
        self.pose_cb_group = MutuallyExclusiveCallbackGroup()  
        self.timer_cb_group = MutuallyExclusiveCallbackGroup() 
        self.event_cb_group = MutuallyExclusiveCallbackGroup()
        self.estop_cb_group = MutuallyExclusiveCallbackGroup()
        # 🔥 [배터리 중계 추가] 배터리 처리용 독립 콜백 그룹
        self.battery_cb_group = MutuallyExclusiveCallbackGroup()

        # =========================================================
        # 1. 목적지 데이터 테이블
        # =========================================================
        self.targets = {
            "START":      {"prefix": "start",  "x": -1.36173, "y": 1.016,  "yaw": 180.0},
            "GO_TO_A":    {"prefix": "area_a", "x": -5.907, "y": 1.106,  "yaw": 0.0},
            "GO_TO_B":    {"prefix": "area_b", "x": -3.193, "y": -2.644, "yaw": 0.0},
            "GO_TO_HOME": {"prefix": "home",   "x": -0.452, "y": -0.063, "yaw": 0.0}
        }

        for cmd, data in self.targets.items():
            prefix = data["prefix"]
            self.declare_parameter(f"{prefix}_x", data["x"])
            self.declare_parameter(f"{prefix}_y", data["y"])
            self.declare_parameter(f"{prefix}_yaw_deg", data["yaw"])

            data["x"] = float(self.get_parameter(f"{prefix}_x").value)
            data["y"] = float(self.get_parameter(f"{prefix}_y").value)
            data["yaw"] = float(self.get_parameter(f"{prefix}_yaw_deg").value)

        # Follower 관련 파라미터 및 변수
        self.declare_parameter("max_follower_dist", 2.0)
        self.declare_parameter("resume_follower_dist", 1.5)
        self.max_f_dist = self.get_parameter("max_follower_dist").value
        self.resume_f_dist = self.get_parameter("resume_follower_dist").value
        
        self.leader_pose = None
        self.follower_pose = None
        self.is_waiting_for_follower = False 
        self.current_goal_pose = None        

        # 상태 변수
        self.current_state = None  
        self.goal_active = False
        self.current_goal_cmd = None 
        self.is_threatened = False   
        self.is_event_paused = False
        
        # 🔥 비상 정지 중복 실행 방지용 플래그 추가
        self.is_estopped = False
        
        # 🔥 [안전장치] 출발 직후 이전 성공 상태를 잘못 읽는 것을 방지
        self.goal_start_time = 0.0 
        
        # =========================================================
        # 통신 설정 (콜백 그룹 지정)
        # =========================================================
        self.state_pub = self.create_publisher(String, 'leader_state', 10)
        self.result_pub = self.create_publisher(String, 'leader_result', self.important_qos) 

        self.audio_pub = self.create_publisher(AudioNoteVector, 'cmd_audio', 10)
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)

        # 🔥 [배터리 중계 추가] 원본 타입을 유지하여 GUI용 토픽 퍼블리셔 생성
        self.battery_relay_pub = self.create_publisher(BatteryState, 'battery_status', 10)

        # 🔥 [String 타입 비상 정지 변경] 구독 타입을 String으로 변경
        self.create_subscription(
            String, '/emergency_stop', self.estop_callback, 10, 
            callback_group=self.estop_cb_group)

        self.create_subscription(
            String, '/leader_cmd', self.cmd_callback, self.important_qos, 
            callback_group=self.cmd_cb_group)

        self.create_subscription(
            PoseWithCovarianceStamped, 'amcl_pose', self.leader_pose_callback, 10,
            callback_group=self.pose_cb_group)
        
        self.create_subscription(
            PoseWithCovarianceStamped, '/robot3/amcl_pose', self.follower_pose_callback, 10, 
            callback_group=self.pose_cb_group)

        self.create_subscription(
            String, '/yolo/detection_status', self.event_callback, self.important_qos,
            callback_group=self.event_cb_group)

        # 🔥 [배터리 중계 추가] 로봇의 실제 배터리 상태 구독
        self.create_subscription(
            BatteryState, 'battery_state', self.battery_callback, 10,
            callback_group=self.battery_cb_group)

        # =========================================================
        # Nav2 시스템 초기화 및 타이머
        # =========================================================
        self.navigator = TurtleBot4Navigator()
        
        self.get_logger().info("⏳ Nav2 시스템 활성화 대기 중...")
        self.get_logger().info("✅ Nav2 시스템 활성화 완료!")

        if not self.navigator.getDockedStatus():
            self.get_logger().info('⚠️ 도킹 해제 상태 감지. 시작 전 도킹을 수행합니다.')
            self.navigator.dock()

        self.create_timer(0.1, self.monitor_nav_status, callback_group=self.timer_cb_group)
        
        # 🔥 [추가] 1.2초마다 정지 조건(팔로워 대기, 이벤트 감지)을 검사하고 사이렌을 내는 타이머
        self.create_timer(1.2, self.siren_loop_callback, callback_group=self.timer_cb_group)
        
        self.set_state("Wait")
        self.get_logger().info("🚀 Flow Chart [Wait] 상태 진입.")


    # =========================================================
    # 🔥 [배터리 중계 추가] 가공 없이 데이터만 토스하는 콜백
    # =========================================================
    def battery_callback(self, msg):
        self.battery_relay_pub.publish(msg)

    # =========================================================
    # 🔥 [추가] 정지 조건 발생 시 사이렌 반복 재생 로직
    # =========================================================
    def siren_loop_callback(self):
        if self.is_estopped:
            return

        if self.is_waiting_for_follower or self.is_event_paused:
            audio_msg = AudioNoteVector()
            audio_msg.append = False
            
            duration = Duration(sec=0, nanosec=300000000)
            note1 = AudioNote(frequency=880, max_runtime=duration)
            note2 = AudioNote(frequency=440, max_runtime=duration)
            
            audio_msg.notes = [note1, note2, note1, note2]
            self.audio_pub.publish(audio_msg)

    # =========================================================
    # 🔥 [String 타입 비상 정지 변경] 콜백 함수 로직 업데이트
    # =========================================================
    def estop_callback(self, msg):
        if self.is_estopped:
            return
        
        estop_cmd = msg.data.strip().upper()

        if estop_cmd in ["STOP", "EMERGENCY"]:
            self.get_logger().fatal(f"🚨 [비상 정지] '{estop_cmd}' 명령 수신! 로봇을 멈추고 노드를 종료합니다.")
            
            self.is_estopped = True 
            
            if self.goal_active:
                self.navigator.cancelTask()

            stop_msg = Twist()
            stop_msg.linear.x = 0.0
            stop_msg.linear.y = 0.0
            stop_msg.linear.z = 0.0
            stop_msg.angular.x = 0.0
            stop_msg.angular.y = 0.0
            stop_msg.angular.z = 0.0
            self.cmd_vel_pub.publish(stop_msg)

            audio_msg = AudioNoteVector()
            audio_msg.append = False
            
            duration = Duration(sec=0, nanosec=300000000)
            
            note1 = AudioNote(frequency=880, max_runtime=duration)
            note2 = AudioNote(frequency=440, max_runtime=duration)
            
            audio_msg.notes = [note1, note2, note1, note2]
            self.audio_pub.publish(audio_msg)

            time.sleep(0.5)

            self.get_logger().fatal("노드 강제 종료 실행!")
            os._exit(0)

    # =========================================================
    # 기존 콜백 함수들
    # =========================================================
    def event_callback(self, msg):
        event_status = msg.data.strip().upper()
        
        # A, B, HOME 이동 중일 때만 이벤트 감지
        if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B", "GO_TO_HOME"]:
            if event_status == "DETECTED" and not self.is_event_paused:
                self.get_logger().warn("🚨 [Event] 이벤트 발생! 로봇 이동을 일시 정지합니다.")
                self.is_event_paused = True
                
                if self.goal_active:
                    self.navigator.cancelTask() 
                self.set_state("Event_Pause")
                
            elif event_status == "CLEAR" and self.is_event_paused:
                self.is_event_paused = False
                
                # 🔥 [수정됨] 이중 잠금: 팔로워 대기 상태라면 출발하지 않음!
                if self.is_waiting_for_follower:
                    self.get_logger().warn("⚠️ [Event] 이벤트는 해제되었으나, 팔로워가 멀어 대기합니다.")
                    self.set_state("Wait_Follower") # 상태창을 팔로워 대기로 전환
                else:
                    self.get_logger().info("✅ [Event] 이벤트 해제! 기존 목적지로 이동을 재개합니다.")
                    
                    if self.goal_active and self.current_goal_pose is not None:
                        self.navigator.goToPose(self.current_goal_pose)
                        self.goal_start_time = time.time() # 쿨타임 초기화
                        
                        if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                            self.set_state("goal_planning")
                        elif self.current_goal_cmd == "GO_TO_HOME":
                            self.set_state("Go_To_HOME")
                    else:
                        self.set_state("Wait")
                        
    def leader_pose_callback(self, msg):
        self.leader_pose = msg.pose.pose.position

    def follower_pose_callback(self, msg):
        self.follower_pose = msg.pose.pose.position

    def get_follower_distance(self):
        if self.leader_pose is None or self.follower_pose is None:
            return -1.0 
        dx = self.leader_pose.x - self.follower_pose.x
        dy = self.leader_pose.y - self.follower_pose.y
        return math.sqrt(dx**2 + dy**2)

    def set_state(self, new_state):
        if self.current_state != new_state:
            self.current_state = new_state
            msg = String()
            msg.data = self.current_state
            self.state_pub.publish(msg)

    def cmd_callback(self, msg):
        cmd = msg.data.strip().upper()

        if self.is_threatened or self.goal_active:
            return 

        if cmd == "START":
            if self.current_state == "Wait":
                self.set_state("Undock")
                if self.navigator.getDockedStatus():
                    self.navigator.undock()
                self.process_movement("START")

        elif cmd in ["GO_TO_A", "GO_TO_B"]:
            if self.current_state == "start_pos":
                self.set_state(f"Go_To_{cmd[-1]}") 
                self.process_movement(cmd)
                
        # 🔥 GUI에서 'GO_TO_HOME' 명령을 받았을 때의 처리 로직
        elif cmd == "GO_TO_HOME":
            self.get_logger().info("GUI로부터 GO_TO_HOME 명령 수신. 홈으로 복귀합니다.")
            self.set_state("Go_To_HOME")
            self.process_movement("GO_TO_HOME")
            
    def process_movement(self, cmd):
        target = self.targets[cmd]
        
        self.current_goal_pose = self.create_pose(target["x"], target["y"], target["yaw"])
        self.navigator.goToPose(self.current_goal_pose)

        self.goal_active = True
        self.current_goal_cmd = cmd
        self.is_waiting_for_follower = False
        self.goal_start_time = time.time() # 🔥 [추가] 목표 지정 후 출발 시간 기록
        
        if cmd not in ["START", "GO_TO_HOME"]:
            self.set_state("goal_planning") 

    def monitor_nav_status(self):
        if not self.goal_active: return
        if self.is_event_paused: return 

        # 🔥 [안전장치 1] 출발 후 1.5초 이내에는 Nav2의 성공 여부 무시
        if time.time() - self.goal_start_time < 1.5:
            return

        dist = self.get_follower_distance()
        if dist >= 0:
            if dist > self.max_f_dist and not self.is_waiting_for_follower and self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                self.get_logger().warn(f"🛑 Follower 거리 멀어짐 ({dist:.2f}m). 정지 및 대기합니다.")
                self.navigator.cancelTask() 
                self.is_waiting_for_follower = True
                self.set_state("Wait_Follower") 
                return 

            elif dist <= self.resume_f_dist and self.is_waiting_for_follower:
                self.get_logger().info(f"▶️ Follower 접근 확인 ({dist:.2f}m). 재출발합니다.")
                self.navigator.goToPose(self.current_goal_pose) 
                self.is_waiting_for_follower = False
                self.goal_start_time = time.time() # 🔥 [추가] 재출발 쿨타임 초기화
                
                if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                    self.set_state("goal_planning")
                elif self.current_goal_cmd == "START":
                    self.set_state("Go_To_START")
                return

        if self.is_waiting_for_follower:
            return

        if self.navigator.isTaskComplete():
            result = self.navigator.getResult()
            
            if result == TaskResult.SUCCEEDED:
                self.goal_active = False 
                if self.current_goal_cmd in ["GO_TO_A", "GO_TO_B"]:
                    self.get_logger().info(f"목적지 도착! 관제소 보고: {self.current_goal_cmd}")
                    report_msg = String()
                    report_msg.data = f"ARRIVED_{self.current_goal_cmd}"
                    self.result_pub.publish(report_msg)

                    self.get_logger().info("목적지 대기 상태 진입. 복귀 명령을 대기합니다.")
                    self.set_state("Wait") 
                    self.current_goal_cmd = None
                
                elif self.current_goal_cmd == "GO_TO_HOME":
                    # 🔥 [안전장치 2] 실제 위치가 HOME 좌표 근처인지 수동으로 한 번 더 확인
                    if self.leader_pose is not None:
                        home_x = self.targets["GO_TO_HOME"]["x"]
                        home_y = self.targets["GO_TO_HOME"]["y"]
                        dist_to_home = math.sqrt((self.leader_pose.x - home_x)**2 + (self.leader_pose.y - home_y)**2)
                        
                        if dist_to_home > 1.0:
                            self.get_logger().warn(f"⚠️ Nav2 비정상 종료 감지! HOME 도착 판단을 보류하고 다시 이동합니다. (잔여 거리: {dist_to_home:.2f}m)")
                            self.navigator.goToPose(self.current_goal_pose)
                            self.goal_active = True
                            self.goal_start_time = time.time()
                            return

                    self.get_logger().info("초기 위치(HOME) 도착 검증 완료! Dock 실행")
                    self.set_state("Dock")
                    if not self.navigator.getDockedStatus():
                        self.navigator.dock()
                    
                    self.set_state("Wait")
                    self.current_goal_cmd = None

                elif self.current_goal_cmd == "START":
                    self.get_logger().info("start_pos 도착 완료. 목적지 명령 대기")
                    self.set_state("start_pos")
                    report_msg = String()
                    report_msg.data = f"ARRIVED_{self.current_goal_cmd}"
                    self.result_pub.publish(report_msg)

            elif result == TaskResult.CANCELED:
                if self.is_waiting_for_follower or self.is_event_paused:
                    pass 
                elif self.is_threatened:
                    self.goal_active = False
                else:
                    self.goal_active = False

    def create_pose(self, x, y, yaw_deg):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.navigator.get_clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        rad = math.radians(yaw_deg)
        pose.pose.orientation.z = math.sin(rad/2)
        pose.pose.orientation.w = math.cos(rad/2)
        return pose

def main(args=None):
    rclpy.init(args=args)
    node = LeaderNode()
    
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    
    try: 
        executor.spin() 
    except KeyboardInterrupt: 
        pass
    finally: 
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()