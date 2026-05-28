let selectedScheduleId = null;
let currentDetectedClass = null;

// 실시간 상태 업데이트 및 팝업 체크
setInterval(() => {
    fetch('/api/status')
        .then(res => res.json())
        .then(data => {
            // 메인 화면에만 있는 요소들이 로그 화면에서 에러를 내지 않도록 확인 후 업데이트
            const sysInfo = document.getElementById('sys-info');
            if(sysInfo) sysInfo.innerText = `CPU: ${data.sysmon.cpu}% | RAM: ${data.sysmon.ram}%`;
            
            const r3Bat = document.getElementById('robot3-bat');
            if(r3Bat) r3Bat.innerText = data.robot_data.robot3_bat;
            
            const r4Bat = document.getElementById('robot4-bat');
            if(r4Bat) r4Bat.innerText = data.robot_data.robot4_bat;
            
            const state3El = document.getElementById('robot3-state');
            const state4El = document.getElementById('robot4-state');
            
            if (state3El && state4El) {
                state3El.innerText = data.robot_data.state;
                state3El.style.color = data.robot_color;
                state4El.innerText = data.robot_data.state;
                state4El.style.color = data.robot_color;
            }
        })
        .catch(err => console.error("Status fetch error:", err));

    fetchSchedules();
    checkPending();
}, 2000);

// 입차 감지 팝업 체크
function checkPending() {
    fetch('/api/get_pending_match')
        .then(res => res.json())
        .then(data => {
            // 감지된 데이터가 있고, 아직 모달이 열리지 않은 경우에만 실행
            if (data && data.class && !currentDetectedClass) {
                const modalImg = document.getElementById('modal-img');
                if (!modalImg) return; // 모달 UI가 없는 페이지라면 여기서 중단

                currentDetectedClass = data.class;
                
                if (data.img) {
                    modalImg.src = data.img;
                    modalImg.style.display = 'block';
                } else {
                    modalImg.style.display = 'none';
                }

                const modalInfo = document.getElementById('modal-info');
                if(modalInfo) modalInfo.innerHTML = `<b>${data.class}</b> 차량이 감지되었습니다.`;
                
                const list = document.getElementById('modal-schedule-list');
                if (list) {
                    if (data.matches && data.matches.length > 0) {
                        list.innerHTML = data.matches.map(m => `
                            <tr onclick="selectScheduleRow(this, ${m.id})" style="cursor:pointer;">
                                <td>${m.time}</td><td>${m.area}</td>
                            </tr>`).join('');
                    } else {
                        list.innerHTML = '<tr><td colspan="2">매칭되는 일정이 없습니다.</td></tr>';
                    }
                }

                const modal = document.getElementById('goNoGoModal');
                if(modal) modal.style.display = 'block';
            }
        })
        .catch(err => console.error("Pending check error:", err));
}

// 스케줄 선택 시 하이라이트
function selectScheduleRow(row, id) {
    document.querySelectorAll('#modal-schedule-list tr').forEach(r => r.classList.remove('selected-row'));
    row.classList.add('selected-row');
    selectedScheduleId = id;
}

// --- 모달 제어 함수 (HTML onclick과 매핑) ---

// 1. 창 닫기 및 초기화
function closeModal() {
    clearPending();
}

// 2. 선택한 스케줄로 출발
function confirmEntry() {
    if (!selectedScheduleId) {
        alert("목록에서 작업 일정을 선택해주세요.");
        return;
    }
    
    const btn = document.getElementById('confirm-btn');
    if(!btn) return;

    const originalText = btn.innerText;
    btn.innerText = "처리 중...";
    btn.disabled = true;

    sendEntryRequest({
        schedule_id: selectedScheduleId,
        class: currentDetectedClass
    }, btn, originalText);
}

// 3. 수동 지정 구역으로 출발
function manualEntry() {
    const manualAreaEl = document.getElementById('manual-area');
    if(!manualAreaEl) return;

    const manualArea = manualAreaEl.value;
    if (!manualArea) {
        alert("이동할 구역을 선택해주세요.");
        return;
    }

    // 브릿지 노드가 이해하는 명령어로 변환 (예: A -> GO_TO_A)
    let finalCommand = manualArea === "A" ? "GO_TO_A" : "GO_TO_B";

    const btn = document.querySelector('.btn-manual');
    if(!btn) return;

    const originalText = btn.innerText;
    btn.innerText = "명령 전송 중...";
    btn.disabled = true;

    sendEntryRequest({
        area: finalCommand,
        class: currentDetectedClass
    }, btn, originalText);
}

// 백엔드 통신 공통 함수
function sendEntryRequest(payload, btnElement, originalText) {
    fetch('/api/admin_confirm', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === "ok") {
            clearPending();
        }
    })
    .catch(err => {
        console.error("Error:", err);
        alert("서버 통신 오류가 발생했습니다.");
    })
    .finally(() => {
        if(btnElement){
            btnElement.innerText = originalText;
            btnElement.disabled = false;
        }
    });
}

function clearPending() {
    fetch('/api/clear_pending_match', { method: 'POST' }).then(() => {
        const modal = document.getElementById('goNoGoModal');
        if(modal) modal.style.display = 'none';
        
        currentDetectedClass = null;
        selectedScheduleId = null;
        
        const manualArea = document.getElementById('manual-area');
        if(manualArea) manualArea.value = '';
        
        fetchSchedules();
    });
}

function fetchSchedules() {
    fetch('/api/get_today_schedules')
        .then(res => res.json())
        .then(data => {
            const tbody = document.getElementById('schedule-table');
            if(!tbody) return; // 테이블이 없는 페이지(로그 화면)면 여기서 중단

            tbody.innerHTML = data.length ? '' : '<tr><td colspan="5">오늘 예정된 작업이 없습니다.</td></tr>';
            data.forEach(item => {
                tbody.innerHTML += `<tr><td>${item.date}</td><td>${item.class}</td><td>${item.time}</td><td>${item.area}</td><td>${item.actual_in ? '✅ 완료' : '대기'}</td></tr>`;
            });
        })
        .catch(err => console.error("Schedules fetch error:", err));
}

function uploadExcel() {
    const fileInput = document.getElementById('excelFile');
    if(!fileInput || !fileInput.files[0]) return alert("파일을 선택해주세요.");
    
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    
    fetch('/api/upload_schedule', { method: 'POST', body: formData })
        .then(res => res.json())
        .then(data => { alert(data.msg); fetchSchedules(); })
        .catch(err => console.error("Upload error:", err));
}

function triggerEmergencyStop() {
    if (!confirm("⚠️ 비상 정지 명령을 전송하시겠습니까?")) return;
    fetch('http://localhost:5001/emergency_stop', { method: 'POST' })
        .then(res => res.json())
        .then(data => { if (data.status === "success") alert("🚨 비상 정지 완료!"); })
        .catch(err => console.error("Emergency stop error:", err));
}