#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
import threading
import sys

class DummyGUI(Node):
    def __init__(self):
        super().__init__('dummy_gui_node')
        
        # LeaderNode로 명령을 보내는 퍼블리셔
        self.cmd_pub = self.create_publisher(String, 'leader_cmd', 10)
        self.event_pub = self.create_publisher(Bool, 'event_trigger', 10)
        
        # LeaderNode의 현재 상태를 확인하기 위한 서브스크라이버
        self.state_sub = self.create_subscription(String, 'leader_state', self.state_callback, 10)
        self.current_leader_state = "Unknown"

    def state_callback(self, msg):
        self.current_leader_state = msg.data

    def publish_cmd(self, cmd_str):
        msg = String()
        msg.data = cmd_str
        self.cmd_pub.publish(msg)
        print(f"\n[GUI ➡️ Leader] 명령 전송: {cmd_str}")

    def publish_event(self, state):
        msg = Bool()
        msg.data = state
        self.event_pub.publish(msg)
        state_str = "🚨 위협 발생 (True)" if state else "✅ 위협 해제 (False)"
        print(f"\n[GUI ➡️ Leader] 이벤트 전송: {state_str}")

# 사용자의 키보드 입력을 처리하는 백그라운드 스레드 함수
def user_input_thread(node):
    menu = """
=================================
       🤖 더미 GUI 테스트 패널
=================================
[1] START 명령 전송
[2] GO_TO_A 명령 전송
[3] GO_TO_B 명령 전송
[4] 🚨 이벤트(Threat) 발생 (True)
[5] ✅ 이벤트(Threat) 해제 (False)
[s] 현재 Leader 상태 확인
[0] 종료
=================================
선택 >> """
    
    while rclpy.ok():
        try:
            choice = input(menu).strip().lower()
            if choice == '1': node.publish_cmd('START')
            elif choice == '2': node.publish_cmd('GO_TO_A')
            elif choice == '3': node.publish_cmd('GO_TO_B')
            elif choice == '4': node.publish_event(True)
            elif choice == '5': node.publish_event(False)
            elif choice == 's': print(f"\n👀 현재 Leader 상태: [{node.current_leader_state}]")
            elif choice == '0':
                print("더미 GUI를 종료합니다.")
                sys.exit(0)
            else:
                print("\n잘못된 입력입니다. 다시 선택해주세요.")
        except Exception:
            break

def main(args=None):
    rclpy.init(args=args)
    node = DummyGUI()
    
    # ROS2 Spin과 키보드 입력을 동시에 처리하기 위해 스레드 사용
    input_thread = threading.Thread(target=user_input_thread, args=(node,), daemon=True)
    input_thread.start()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()