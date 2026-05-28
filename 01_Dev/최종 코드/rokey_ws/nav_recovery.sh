#!/bin/bash
source /opt/ros/humble/setup.bash

# 2. Nav2 lifecycle 순서 리스트 정의
readonly STEPS=(
  "controller_server"
  "smoother_server"
  "planner_server"
  "behavior_server"
  "bt_navigator"
  "waypoint_follower"
  "velocity_smoother"
)

# 색상 정의
WHITE='\033[1;37m'
L_YELLOW='\033[38;5;229m'
YELLOW='\033[1;33m'
RESET='\033[0m'

clear
echo ""
echo -e "${L_YELLOW}                     XXXXXXXXXX                    ${RESET}"
echo -e "${L_YELLOW}                    X          X                   ${RESET}"
echo -e "${L_YELLOW}                     XXXXXXXXXX                    ${RESET}"
echo "                                                   "
echo "                   XXXXXXXXXXXX                   "
echo "              XXX XX            XX XXXX            "
echo "             X   X                X    X           "
echo "            X                           X          "
echo "    ✨       X    X                  X   X          " 
echo "             XXXX   XXX      XXX     XXX           "
echo -e "${L_YELLOW}    X          ${RESET}X    XXX      XXX     X             "
echo -e "${L_YELLOW}   XXX         ${RESET}X                     X             "
echo -e "${L_YELLOW} XXXXXXXX      ${RESET}X                     X             "
echo -e "${L_YELLOW}  XXXXXX       ${RESET}X         X           X             "
echo -e "${L_YELLOW}  XXX XX       ${RESET}X       XX XX         X             "
echo "     X          XX      XXX        XX    XXXXXXXX  "
echo "      X           XXXXXXXXXXXXXXXXX  XXXXX       X "
echo "       X        XX                 XXX            X"
echo "        X XXXXXX          XXXXX     X       X     X"
echo "         XX              X           XX     XXXXXX    "
echo "          XXXXXX          XXXXXX     X XXXXX       "
echo "               X                     X             "
echo -e "\n${WHITE}ଘ(੭ˊᵕˋ)੭* 🌷${RESET} ${YELLOW}Nav2 Recovery Magic Starting! ${RESET}"

# --- Step 정보 안내 출력 ---
echo -e "\n=========================================="
echo -e "       Nav2 Lifecycle Step List"
echo -e "=========================================="
for i in "${!STEPS[@]}"; do
  # 사용자는 1부터 입력하므로 인덱스에 +1을 해서 보여줍니다.
  printf "  Step [%d]: %s\n" $((i+1)) "${STEPS[$i]}"
done
echo -e "==========================================\n"

# 메인 루프
while true; do
  # 1-1. 사용자 입력1: 로봇 네임스페이스 (0-9 제한)
  while true; do
    read -p "로봇 네임스페이스 숫자 입력 (0-9): " ns || { echo ""; return 0 2>/dev/null || exit 0; }
    if [[ "$ns" =~ ^[0-9]$ ]]; then
      break
    else
      echo "오류: 네임스페이스는 0에서 9 사이의 숫자여야 합니다."
    fi
  done
  
  current_robot="robot${ns}"

  # 내부 루프
  while true; do
    # 1-2. 사용자 입력2: 실패한 step 인덱스 (1-7 제한)
    while true; do
      read -p "실패한 Step 인덱스 (1-7): " idx || { echo ""; return 0 2>/dev/null || exit 0; }
      if [[ "$idx" =~ ^[1-7]$ ]]; then
        break
      else
        echo "오류: 인덱스는 1에서 7 사이여야 합니다."
      fi
    done

    echo "------------------------------------------"
    echo "현재 대상: $current_robot"
    echo "복구 범위: ${STEPS[$idx-1]} 부터 마지막까지"
    echo "------------------------------------------"

    # 4. 입력받은 단계부터 마지막까지 명령어 실행
    for (( i=idx-1; i<${#STEPS[@]}; i++ )); do
      current_step=${STEPS[$i]}
      
      echo "[실행] /$current_robot/$current_step 설정 및 활성화 중..."
      
      # 실제 ROS 2 명령어 실행
      ros2 lifecycle set "/$current_robot/$current_step" configure
      ros2 lifecycle set "/$current_robot/$current_step" activate
    done

    echo "------------------------------------------"
    echo "작업이 완료되었습니다."

    # 5. 추가 작업 선택
    read -p "추가 작업 - 추가 복구(a), 로봇 변경(r), 종료(d): " option || { echo ""; return 0 2>/dev/null || exit 0; }

    case $option in
      [a,A]) 
        continue 
        ;;
      [r,R]) 
        break 
        ;;
      [d,D]) 
        echo "스크립트를 종료합니다."
        return 0 2>/dev/null || exit 0
        ;;
      *) 
        echo "잘못된 입력입니다. 종료합니다."
        return 1 2>/dev/null || exit 1
        ;;
    esac
  done
done
