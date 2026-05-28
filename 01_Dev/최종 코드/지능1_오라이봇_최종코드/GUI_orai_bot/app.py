import sqlite3
import os
import pandas as pd
import requests
import psutil
import time
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime

app = Flask(__name__)
app.secret_key = "orai_bot_leo_key"

# --- 데이터베이스 초기화 ---
def init_db():
    with sqlite3.connect('orai_bot.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            date TEXT, class_name TEXT, start_time TEXT, target_area TEXT, actual_in TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            event_type TEXT, content TEXT, start_time TEXT, image_path TEXT)''')
        conn.commit()

# --- 전역 상태 변수 ---
robot_data = {
    "robot3_bat": 0,
    "robot4_bat": 0,
    "state": "대기중"
}
last_heartbeat_time = 0
pending_match = None 

@app.route('/api/status')
def get_status():
    global last_heartbeat_time,robot_data
    if last_heartbeat_time != 0 and (time.time() - last_heartbeat_time > 300):
        robot_data["state"] = "연결 끊김"
        robot_color = "#95a5a6"
    else:
        robot_color = "#e74c3c" if "EMERGENCY" in robot_data["state"] else "#2ecc71"
    
    return jsonify({
        "sysmon": {"cpu": psutil.cpu_percent(), "ram": psutil.virtual_memory().percent},
        "robot_data": robot_data,
        "robot_color": robot_color
    })

@app.route('/api/update_robot_status', methods=['POST'])
def update_status():
    global last_heartbeat_time, robot_data
    last_heartbeat_time = time.time()
    data = request.json

    if 'robot3_bat' in data:
        robot_data['robot3_bat'] = data['robot3_bat']
    if 'robot4_bat' in data:
        robot_data['robot4_bat'] = data['robot4_bat']
    if 'status' in data:
        robot_data['state'] = data['status']
    return jsonify({"status": "ok"})

@app.route('/api/log_event', methods=['POST'])
def log_event():
    data = request.json
    with sqlite3.connect('orai_bot.db') as conn:
        conn.execute("INSERT INTO events (event_type, content, start_time, image_path) VALUES (?,?,?,?)",
                     (data.get('type'), data.get('content'), datetime.now().strftime('%Y-%m-%d %H:%M:%S'), data.get('img_path')))
    return jsonify({"status": "ok"})

@app.route('/api/detect_object', methods=['POST'])
def detect_object():
    global pending_match
    data = request.json
    obj_class = data.get('class', '').strip()
    img_path = data.get('img_path')
    today = datetime.now().strftime('%Y.%m.%d')
    with sqlite3.connect('orai_bot.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, target_area, start_time FROM schedules WHERE date=? AND UPPER(class_name)=UPPER(?) AND actual_in IS NULL", (today, obj_class))
        res = c.fetchall()
        pending_match = {
            "class": obj_class, 
            "img": img_path, 
            "matches": [{"id": r[0], "area": r[1], "time": r[2]} for r in res]
        }
    return jsonify({"status": "match"})

@app.route('/api/get_pending_match')
def get_pending_match():
    return jsonify(pending_match)

@app.route('/api/clear_pending_match', methods=['POST'])
def clear_pending_match():
    global pending_match
    pending_match = None
    return jsonify({"status": "ok"})

@app.route('/api/admin_confirm', methods=['POST'])
def admin_confirm():
    global robot_data
    data = request.json
    sid = data.get('schedule_id')
    manual_area = data.get('area')
    obj_class = data.get('class', 'Unknown')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    area = ""

    with sqlite3.connect('orai_bot.db') as conn:
        if sid:
            c = conn.cursor()
            c.execute("SELECT target_area FROM schedules WHERE id=?", (sid,))
            res = c.fetchone()
            if res:
                area = res[0]
                conn.execute("UPDATE schedules SET actual_in=? WHERE id=?", (now, sid))
                conn.execute("INSERT INTO events (event_type, content, start_time) VALUES (?,?,?)", 
                             ("출발", f"[{obj_class}] {area} 이동 시작", now))
        elif manual_area:
            area = manual_area
            conn.execute("INSERT INTO schedules (date, class_name, start_time, target_area, actual_in) VALUES (?,?,?,?,?)", 
                         (datetime.now().strftime('%Y.%m.%d'), obj_class, "수동", area, now))
            conn.execute("INSERT INTO events (event_type, content, start_time) VALUES (?,?,?)", 
                         ("수동출발", f"[미등록]{area} 강제 투입", now))
        conn.commit()
        if area:
            robot_data["state"] = "이동 준비 중"
            try: requests.post("http://localhost:5001/move_robot", json={"area": area}, timeout=0.5)
            except: pass
    return jsonify({"status": "ok"})

@app.route('/api/get_today_schedules')
def get_today_schedules():
    today = datetime.now().strftime('%Y.%m.%d')
    with sqlite3.connect('orai_bot.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, date, class_name, target_area, start_time, actual_in FROM schedules WHERE date=?", (today,))
        return jsonify([{"id":r[0], "date":r[1],"class":r[2],"area":r[3],"time":r[4],"actual_in":r[5]} for r in c.fetchall()])

@app.route('/api/get_events')
def get_events():
    with sqlite3.connect('orai_bot.db') as conn:
        c = conn.cursor()
        c.execute("SELECT start_time, event_type, content, image_path FROM events ORDER BY id DESC")
        return jsonify([{"time":r[0], "type":r[1], "content":r[2], "img":r[3]} for r in c.fetchall()])

@app.route('/api/upload_schedule', methods=['POST'])
def upload():
    file = request.files.get('file')
    if not file: return jsonify({"status": "error", "msg": "파일 없음"})
    try:
        df = pd.read_excel(file, engine='openpyxl')
        with sqlite3.connect('orai_bot.db') as conn:
            for _, row in df.iterrows():
                f_date = pd.to_datetime(row['날짜']).strftime('%Y.%m.%d')
                conn.execute("INSERT INTO schedules (date, class_name, start_time, target_area) VALUES (?,?,?,?)", 
                             (f_date, str(row['클래스명']), str(row['시작시간']), str(row['작업구역'])))
        return jsonify({"status": "ok", "msg": "업로드 성공"})
    except Exception as e: return jsonify({"status": "error", "msg": str(e)})

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and request.form['username'] == 'admin' and request.form['password'] == '1234':
        session['logged_in'] = True
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/logs')
def logs():
    return render_template('logs.html')

@app.route('/api/get_all_records')
def get_all_records():
    target_table = request.args.get('table', 'events')
    
    with sqlite3.connect('orai_bot.db') as conn:
        conn.row_factory = sqlite3.Row 
        c = conn.cursor()
        
        if target_table == 'schedules':
            c.execute("SELECT date, class_name, start_time, actual_in, target_area FROM schedules ORDER BY id DESC")
        else:
            c.execute("SELECT start_time, event_type, content, image_path FROM events ORDER BY id DESC")
            
        rows = c.fetchall()
        return jsonify([dict(row) for row in rows])

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)