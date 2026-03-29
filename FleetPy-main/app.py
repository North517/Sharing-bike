from flask import Flask, render_template, jsonify, request, redirect, url_for, session, g
import os
import json
import math
import sqlite3
import hashlib
import pandas as pd
import random
import sys
import shutil
from functools import wraps
from datetime import datetime

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FLEETPY_MAIN_DIR)

app = Flask(__name__)
app.secret_key = 'fleetpy_shanxi_agri_2025_secret'

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(FLEETPY_MAIN_DIR, 'users.db')

_current_preset_index = 0
NUM_PRESETS = 3

# ─────────────────────────────────────────
# 数据库初始化
# ─────────────────────────────────────────
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    """初始化数据库，创建用户表并插入默认账号"""
    with app.app_context():
        db = sqlite3.connect(DB_PATH)
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                username  TEXT UNIQUE NOT NULL,
                password  TEXT NOT NULL,
                role      TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        ''')
        db.execute('''
            CREATE TABLE IF NOT EXISTS login_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL,
                login_time TEXT NOT NULL,
                ip         TEXT
            )
        ''')
        db.commit()
        # 插入默认账号（如不存在）
        for uname, pwd, role in [('admin', 'admin123', 'admin'), ('demo', 'demo2025', 'user')]:
            exists = db.execute('SELECT id FROM users WHERE username=?', (uname,)).fetchone()
            if not exists:
                db.execute(
                    'INSERT INTO users (username, password, role, created_at) VALUES (?,?,?,?)',
                    (uname, hash_password(pwd), role, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
        db.commit()
        db.close()

# ─────────────────────────────────────────
# 装饰器
# ─────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return jsonify({'error': '权限不足，需要管理员账号'}), 403
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────
def _load_sim_data():
    path = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _calc_dist(lon1, lat1, lon2, lat2):
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110540
    return math.sqrt(dx*dx + dy*dy)

# ─────────────────────────────────────────
# 认证路由
# ─────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username=? AND password=?',
            (username, hash_password(password))
        ).fetchone()
        if user:
            session['logged_in'] = True
            session['username'] = username
            session['role'] = user['role']
            session['user_id'] = user['id']
            # 记录登录时间和日志
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            db.execute('UPDATE users SET last_login=? WHERE id=?', (now, user['id']))
            db.execute('INSERT INTO login_log (username, login_time, ip) VALUES (?,?,?)',
                      (username, now, request.remote_addr))
            db.commit()
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误，请重试。'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ─────────────────────────────────────────
# 主页面路由
# ─────────────────────────────────────────
@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/data_analysis')
@login_required
def data_analysis():
    return render_template('data_analysis.html')

@app.route('/configuration')
@login_required
def configuration():
    return render_template('configuration.html')

@app.route('/events')
@login_required
def events():
    return render_template('events.html')

@app.route('/heatmap')
@login_required
def heatmap():
    return render_template('heatmap.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/user_mgmt')
@admin_required
def user_mgmt():
    return render_template('user_mgmt.html')

# ─────────────────────────────────────────
# 用户管理 API（仅管理员）
# ─────────────────────────────────────────
@app.route('/api/users')
@admin_required
def api_users():
    db = get_db()
    users = db.execute('SELECT id, username, role, created_at, last_login FROM users').fetchall()
    return jsonify([dict(u) for u in users])

@app.route('/api/users', methods=['POST'])
@admin_required
def api_create_user():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'user')
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    db = get_db()
    try:
        db.execute(
            'INSERT INTO users (username, password, role, created_at) VALUES (?,?,?,?)',
            (username, hash_password(password), role, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        db.commit()
        return jsonify({'message': f'用户 {username} 创建成功'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': f'用户名 {username} 已存在'}), 409

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({'error': '不能删除当前登录账号'}), 400
    db = get_db()
    user = db.execute('SELECT username FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    db.execute('DELETE FROM users WHERE id=?', (user_id,))
    db.commit()
    return jsonify({'message': f'用户 {user["username"]} 已删除'})

@app.route('/api/users/<int:user_id>/password', methods=['PUT'])
@admin_required
def api_reset_password(user_id):
    data = request.get_json()
    new_password = data.get('password', '').strip()
    if not new_password:
        return jsonify({'error': '新密码不能为空'}), 400
    db = get_db()
    db.execute('UPDATE users SET password=? WHERE id=?', (hash_password(new_password), user_id))
    db.commit()
    return jsonify({'message': '密码已重置'})

@app.route('/api/login_log')
@admin_required
def api_login_log():
    db = get_db()
    logs = db.execute('SELECT * FROM login_log ORDER BY id DESC LIMIT 50').fetchall()
    return jsonify([dict(l) for l in logs])

# ─────────────────────────────────────────
# 仿真数据 API
# ─────────────────────────────────────────
@app.route('/simulation_data.json')
@login_required
def get_simulation_data():
    file_path = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'application/json'}
    return jsonify({'error': 'simulation_data.json not found'}), 404

@app.route('/api/stats')
@login_required
def api_stats():
    try:
        data = _load_sim_data()
        frames = data.get('frames', [])
        total_duration = data.get('total_duration', 600)
        if not frames:
            return jsonify({'error': 'no frames'}), 500

        num_frames = len(frames)
        num_vehicles = len(frames[0].get('vehicles', []))
        num_bikes_total = len(frames[0].get('bikes', []))

        bike_ids_prev = set(b['id'] for b in frames[0].get('bikes', []))
        bike_collect_frame = {}
        for fi, frame in enumerate(frames[1:], 1):
            cur_ids = set(b['id'] for b in frame.get('bikes', []))
            disappeared = bike_ids_prev - cur_ids
            for bid in disappeared:
                if bid not in bike_collect_frame:
                    bike_collect_frame[bid] = fi
            bike_ids_prev = cur_ids
        total_collected = len(bike_collect_frame)

        remaining_series = [len(f.get('bikes', [])) for f in frames]

        parking_lons = [p['lon'] for p in frames[0].get('parking_spots', [])]
        parking_lats = [p['lat'] for p in frames[0].get('parking_spots', [])]

        def at_parking(v):
            for plon, plat in zip(parking_lons, parking_lats):
                if _calc_dist(v['lon'], v['lat'], plon, plat) < 30:
                    return True
            return False

        busy_series = [sum(1 for v in frame.get('vehicles', []) if not at_parking(v)) for frame in frames]
        avg_utilization = sum(busy_series) / (num_frames * max(num_vehicles, 1)) * 100

        vehicle_distances = {}
        for fi in range(1, num_frames):
            prev_v = {v['id']: v for v in frames[fi-1].get('vehicles', [])}
            for v in frames[fi].get('vehicles', []):
                vid = v['id']
                if vid in prev_v:
                    d = _calc_dist(prev_v[vid]['lon'], prev_v[vid]['lat'], v['lon'], v['lat'])
                    vehicle_distances[vid] = vehicle_distances.get(vid, 0) + d
        total_distance_m = sum(vehicle_distances.values())

        bike_init_pos = {b['id']: (b['lon'], b['lat']) for b in frames[0].get('bikes', [])}
        collect_distances = []
        for bid, fi in bike_collect_frame.items():
            if bid not in bike_init_pos:
                continue
            blon, blat = bike_init_pos[bid]
            frame = frames[min(fi, num_frames-1)]
            for v in frame.get('vehicles', []):
                collect_distances.append(_calc_dist(v['lon'], v['lat'], blon, blat))
                break
        avg_collect_dist = sum(collect_distances) / len(collect_distances) if collect_distances else 0

        parking_spots = frames[0].get('parking_spots', [])
        station_collect = {p['id']: 0 for p in parking_spots}
        v0_vehicles = frames[0].get('vehicles', [])
        vehicle_home = {}
        for v in v0_vehicles:
            best_p, best_d = None, 1e9
            for p in parking_spots:
                d = _calc_dist(v['lon'], v['lat'], p['lon'], p['lat'])
                if d < best_d:
                    best_d = d
                    best_p = p['id']
            vehicle_home[v['id']] = best_p
        v_collected_prev = {v['id']: v.get('has_bike', False) for v in frames[0].get('vehicles', [])}
        for fi, frame in enumerate(frames[1:], 1):
            for v in frame.get('vehicles', []):
                vid = v['id']
                now_has = v.get('has_bike', False)
                if now_has and not v_collected_prev.get(vid, False):
                    home = vehicle_home.get(vid)
                    if home and home in station_collect:
                        station_collect[home] += 1
                v_collected_prev[vid] = now_has

        segment_size = max(1, num_frames // 10)
        time_segments = []
        for i in range(0, num_frames, segment_size):
            count = sum(1 for _, cf in bike_collect_frame.items() if i <= cf < i + segment_size)
            t_min = frames[i]['time'] / 60 if frames[i]['time'] else i * total_duration / num_frames / 60
            time_segments.append({'time_min': round(t_min, 1), 'count': count})

        events = []
        v_has_bike_prev = {v['id']: False for v in frames[0].get('vehicles', [])}
        v_at_park_prev = {v['id']: True for v in frames[0].get('vehicles', [])}
        for fi, frame in enumerate(frames):
            t = frame.get('time', fi)
            time_str = f'{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}'
            for v in frame.get('vehicles', []):
                vid = v['id']
                now_has = v.get('has_bike', False)
                now_park = at_parking(v)
                if not v_has_bike_prev.get(vid) and now_has:
                    events.append({'time': time_str, 'vehicle': vid, 'type': '捡起单车', 'desc': f'{vid} 收集了一辆散落单车'})
                if now_park and not v_at_park_prev.get(vid):
                    events.append({'time': time_str, 'vehicle': vid, 'type': '返回车站', 'desc': f'{vid} 返回停车站'})
                if not now_park and v_at_park_prev.get(vid) and fi > 0:
                    events.append({'time': time_str, 'vehicle': vid, 'type': '从车站出发', 'desc': f'{vid} 出发执行收车任务'})
                v_has_bike_prev[vid] = now_has
                v_at_park_prev[vid] = now_park
        events = events[:200]

        heat_points = []
        sample_step = max(1, num_frames // 60)
        for fi in range(0, num_frames, sample_step):
            for b in frames[fi].get('bikes', []):
                heat_points.append([b['lat'], b['lon'], 0.6])

        return jsonify({
            'total_duration_min': round(total_duration / 60, 1),
            'num_vehicles': num_vehicles,
            'num_bikes_total': num_bikes_total,
            'total_collected': total_collected,
            'avg_utilization_pct': round(avg_utilization, 1),
            'total_distance_m': round(total_distance_m),
            'avg_collect_dist_m': round(avg_collect_dist),
            'vehicle_distances': {k: round(v) for k, v in vehicle_distances.items()},
            'busy_series': busy_series[::max(1, num_frames//100)],
            'remaining_series': remaining_series[::max(1, num_frames//100)],
            'station_collect': station_collect,
            'time_segments': time_segments,
            'events': events,
            'heat_points': heat_points,
            'initial_map_view': data.get('initial_map_view', {}),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/resimulate', methods=['POST'])
@login_required
def resimulate():
    global _current_preset_index
    try:
        _current_preset_index = (_current_preset_index + 1) % NUM_PRESETS
        preset_file = os.path.join(FLEETPY_MAIN_DIR, f'simulation_data_preset_{_current_preset_index}.json')
        target_file = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
        if not os.path.exists(preset_file):
            return jsonify({'error': f'Preset file not found: {preset_file}'}), 500
        shutil.copy(preset_file, target_file)
        return jsonify({'message': f'已切换到预设方案 {_current_preset_index + 1}，单车重新分布完成！', 'preset': _current_preset_index}), 200
    except Exception as e:
        return jsonify({'error': f'切换预设失败: {str(e)}'}), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=8000)
