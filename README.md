# 🤖 오라이봇 (Orai Bot)

**오라이봇**은 공사 현장에서의 안전한 차량 안내를 위한 **지능형 AMR(Autonomous Mobile Robot) Leader-Follower 시스템**입니다. 
ROS 2 기반의 자율 주행 로봇(Turtlebot4) 2대와 YOLO 기반의 비전 인식 기술, 그리고 관제용 Web GUI를 결합하여 효율적인 작업 지시 및 모니터링을 지원합니다.

## 🌟 주요 기능 (Key Features)

- **자율 주행 및 군집 주행 (Leader-Follower)**
  - `Leader 로봇`: 지정된 구역(A Zone, B Zone 등)으로 스스로 목적지를 찾아 이동합니다.
  - `Follower 로봇`: 비전(YOLO) 및 뎁스(Depth) 카메라를 사용하여 앞서가는 Leader 로봇이나 특정 타겟을 인식하고 안정적으로 추종합니다.
- **AI 비전 인식 (Object Detection)**
  - YOLO 모델을 활용한 객체 인식 및 분류 (지게차, 트럭 등 물류 환경 객체 타겟팅).
  - Depth 카메라를 연동한 3D 거리 측정 및 추적 제어 보조.
- **웹 기반 관제 시스템 (Web GUI)**
  - Flask 기반 웹 서버를 통한 로봇 상태(배터리, 현재 상태, 시스템 리소스) 실시간 모니터링.
  - 엑셀(Excel) 스케줄 업로드 및 작업 지시 기능.
  - 이벤트 로그 및 객체 인식 결과 확인 (SQLite 데이터베이스 연동).

## 🛠 기술 스택 (Tech Stack)

- **Robotics**: ROS 2, Turtlebot4, Nav2
- **AI & Vision**: OpenCV, YOLO (PyTorch), Depth Camera API
- **Backend (Web GUI)**: Python, Flask, SQLite3, Pandas
- **Frontend**: HTML/CSS/JS

## 📁 프로젝트 주요 구조 (Project Structure)

```text
.
├── 01_Dev/                 # ROS 2 워크스페이스 및 커스텀 패키지 소스 코드 
│                           # (Leader/Follower 제어, YOLO 기반 비전 노드 등)
├── 02_Project_Log/         # 프로젝트 산출물 
│                           # (설계도, PPT, 시연 영상, 최종 제출 소스 코드 및 Web GUI 서버)
├── 99_Archive/             # 아카이브 및 테스트용 코드 모음
└── README.md               # 프로젝트 설명 파일
```

## 🚀 시작하기 (Getting Started)

### 1. 웹 서버(관제 시스템) 실행
```bash
cd "02_Project_Log/지능1_오라이봇_산출물/지능1_오라이봇_제출 폴더/소스코드 폴더"
python3 app.py
```
> 브라우저에서 `http://localhost:5000` 으로 접속하여 관제 시스템을 확인할 수 있습니다.
> (기본 관리자 계정 - ID: `admin`, PW: `1234`)

### 2. ROS 2 패키지 빌드 및 실행
```bash
cd "01_Dev/최종 코드/rokey_ws"
colcon build --symlink-install
source install/setup.bash
# 이후 Leader/Follower launch 파일 또는 Python 노드 실행
```

## 🎥 시연 및 산출물
`02_Project_Log` 폴더 내에 프로젝트 **시스템 설계도(`drawio`, `docx`)** 및 각 기능별 **시연 영상(`.mp4`)** 이 포함되어 있어 상세한 구동 방식을 확인할 수 있습니다.

---
*이 프로젝트는 로봇 기반 지능형 자동화(물류 등) 구현을 목표로 개발되었습니다.*
