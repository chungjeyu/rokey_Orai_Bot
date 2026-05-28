import rclpy                                          # ROS2 파이썬 라이브러리 임포트
from rclpy.node import Node                           # ROS2 노드 클래스 임포트
from irobot_create_msgs.msg import AudioNoteVector, AudioNote # 터틀봇 전용 오디오 메시지 타입 임포트

class Turtlebot4Beeper(Node):                         # Node를 상속받는 비퍼 클래스 정의
    def __init__(self):                               # 클래스 초기화 함수
        super().__init__('turtlebot4_beeper')         # 노드 이름을 'turtlebot4_beeper'로 등록
        
        self.audio_pub = self.create_publisher(       # 데이터를 보낼 퍼블리셔 생성
            AudioNoteVector,                          # 메시지 타입: 오디오 노트 리스트
            '/robot3/cmd_audio',                      # 토픽 경로: 로봇3의 오디오 제어 주소
            10)                                       # 큐 사이즈: 통신 지연 대비 10개 저장
        
        self.timer = self.create_timer(1.0, self.play_alert_sound) # 1초 뒤에 소리 재생 함수 실행 예약

    def play_alert_sound(self):                       # 실제 소리를 조립하고 전송하는 함수
        self.timer.cancel()                           # 소리가 반복되지 않게 타이머 종료
        
        msg = AudioNoteVector()                       # 노래 바구니(메시지 객체) 생성
        msg.append = False                            # 기존 소리가 있다면 끊고 새로 시작
        
        # [주파수(Hz), 지속시간(ns)] 리스트 정의
        beep_sequence = [(880, 300000000), (440, 300000000), (880, 300000000), (440, 300000000)]
        
        for freq, nano in beep_sequence:              # 리듬을 하나씩 꺼내서 조립
            note = AudioNote()                        # 개별 음표 객체 생성
            note.frequency = int(freq)                # 주파수 입력 (에러 방지를 위해 반드시 정수형 변환)
            note.max_runtime.sec = 0                  # 초 단위 시간 설정 (0초)
            note.max_runtime.nanosec = nano           # 나노초 단위 시간 설정 (0.3초)
            msg.notes.append(note)                    # 조립된 음표를 노래 바구니에 추가
            
        self.audio_pub.publish(msg)                   # 완성된 노래 바구니를 로봇으로 전송
        self.get_logger().info('로봇3 삐뽀삐뽀 재생!') # 터미널에 실행 상태 출력

def main(args=None):                                  # 프로그램 시작점
    rclpy.init(args=args)                             # ROS2 통신 환경 초기화
    node = Turtlebot4Beeper()                         # 위 클래스를 실제 노드 객체로 생성
    try:
        rclpy.spin(node)                              # 노드를 종료하지 않고 계속 실행 상태 유지
    except KeyboardInterrupt:                         # Ctrl+C 입력 시 안전하게 종료 처리
        pass
    finally:
        node.destroy_node()                           # 노드 메모리 해제
        rclpy.shutdown()                              # ROS2 시스템 종료

if __name__ == '__main__':                            # 이 파일이 직접 실행될 때 main 함수 호출
    main()
