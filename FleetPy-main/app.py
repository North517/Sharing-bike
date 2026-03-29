from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import os
import json
import math
import pandas as pd
import random
import sys
import shutil
from functools import wraps

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FLEETPY_MAIN_DIR)

app = Flask(__name__)
app.secret_key = 'fleetpy_shanxi_agri_2025_secret'

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))

# 当前预设索引（0/1/2 循环切换）
_current_preset_index = 0
NUM_PRESETS = 3

# 账户配置（用户名: 密码）
USERS = {
    'admin': 'admin123',
    'demo':  'demo2025',
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def _load_sim_data():
    path = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _calc_dist(lon1, lat1, lon2, lat2):
    """经纬度距离（米，简化版）"""
    dx = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1 + lat2) / 2))
    dy = (lat2 - lat1) * 110540
    return math.sqrt(dx*dx + dy*dy)


@app.route('/api/stats')
@login_required
def api_stats():
    """从 simulation_data.json 提取真实统计数据供各页面使用"""
    try:
        data = _load_sim_data()
        frames = data.get('frames', [])
        total_duration = data.get('total_duration', 600)
        if not frames:
            return jsonify({'error': 'no frames'}), 500

        num_frames = len(frames)
        num_vehicles = len(frames[0].get('vehicles', []))
        num_bikes_total = len(frames[0].get('bikes', []))

        # ── 统计每辆单车的收集帧（第一次从有到无）
        bike_ids_prev = set(b['id'] for b in frames[0].get('bikes', []))
        bike_collect_frame = {}  # bike_id -> frame_index
        for fi, frame in enumerate(frames[1:], 1):
            cur_ids = set(b['id'] for b in frame.get('bikes', []))
            disappeared = bike_ids_prev - cur_ids
            for bid in disappeared:
                if bid not in bike_collect_frame:
                    bike_collect_frame[bid] = fi
            bike_ids_prev = cur_ids
        total_collected = len(bike_collect_frame)

        # ── 各帧剩余单车数（时间序列）
        remaining_series = [len(f.get('bikes', [])) for f in frames]

        # ── 每帧忙碌车辆数（has_bike=True 或 not at parking）
        parking_lons = [p['lon'] for p in frames[0].get('parking_spots', [])]
        parking_lats = [p['lat'] for p in frames[0].get('parking_spots', [])]

        def at_parking(v):
            for plon, plat in zip(parking_lons, parking_lats):
                if _calc_dist(v['lon'], v['lat'], plon, plat) < 30:
                    return True
            return False

        busy_series = []
        for frame in frames:
            busy = sum(1 for v in frame.get('vehicles', []) if not at_parking(v))
            busy_series.append(busy)

        avg_utilization = sum(busy_series) / (num_frames * max(num_vehicles, 1)) * 100

        # ── 每辆车的行驶距离
        vehicle_distances = {}
        for fi in range(1, num_frames):
            prev_v = {v['id']: v for v in frames[fi-1].get('vehicles', [])}
            for v in frames[fi].get('vehicles', []):
                vid = v['id']
                if vid in prev_v:
                    d = _calc_dist(prev_v[vid]['lon'], prev_v[vid]['lat'], v['lon'], v['lat'])
                    vehicle_distances[vid] = vehicle_distances.get(vid, 0) + d
        total_distance_m = sum(vehicle_distances.values())

        # ── 每辆单车被收集时的取车距离（估算：收集帧时最近无人车到该bike的距离）
        collect_distances = []
        # 记录每辆bike初始位置
        bike_init_pos = {b['id']: (b['lon'], b['lat']) for b in frames[0].get('bikes', [])}
        for bid, fi in bike_collect_frame.items():
            if bid not in bike_init_pos:
                continue
            blon, blat = bike_init_pos[bid]
            frame = frames[min(fi, num_frames-1)]
            for v in frame.get('vehicles', []):
                d = _calc_dist(v['lon'], v['lat'], blon, blat)
                collect_distances.append(d)
                break  # 取第一辆
        avg_collect_dist = sum(collect_distances) / len(collect_distances) if collect_distances else 0

        # ── 按停车站统计收集量
        parking_spots = frames[0].get('parking_spots', [])
        station_collect = {p['id']: 0 for p in parking_spots}
        # 用车辆归属站点（起点最近站点）判断
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
        # 按帧统计各车收车事件
        v_collected_prev = {v['id']: v.get('has_bike', False) for v in frames[0].get('vehicles', [])}
        for fi, frame in enumerate(frames[1:], 1):
            for v in frame.get('vehicles', []):
                vid = v['id']
                now_has = v.get('has_bike', False)
                prev_has = v_collected_prev.get(vid, False)
                if now_has and not prev_has:
                    home = vehicle_home.get(vid)
                    if home and home in station_collect:
                        station_collect[home] += 1
                v_collected_prev[vid] = now_has

        # ── 按时间段（每100帧一段）统计收车数
        segment_size = max(1, num_frames // 10)
        time_segments = []
        for i in range(0, num_frames, segment_size):
            seg_end = min(i + segment_size, num_frames)
            count = sum(1 for _, cf in bike_collect_frame.items() if i <= cf < seg_end)
            t_min = frames[i]['time'] / 60 if frames[i]['time'] else i * total_duration / num_frames / 60
            time_segments.append({'time_min': round(t_min, 1), 'count': count})

        # ── 事件时间线
        events = []
        v_has_bike_prev = {v['id']: False for v in frames[0].get('vehicles', [])}
        v_at_park_prev = {v['id']: True for v in frames[0].get('vehicles', [])}
        for fi, frame in enumerate(frames):
            t = frame.get('time', fi)
            h = str(t // 3600).zfill(2)
            m = str((t % 3600) // 60).zfill(2)
            s = str(t % 60).zfill(2)
            time_str = f'{h}:{m}:{s}'
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
        # 按时间排序，最多返回200条
        events = events[:200]

        # ── 热力图数据（全程所有帧的单车位置，采样减量）
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
            'busy_series': busy_series[::max(1, num_frames//100)],  # 采样
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            error = '用户名或密码错误，请重试。'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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

@app.route('/simulation_data.json')
@login_required
def get_simulation_data():
    file_path = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'application/json'}
    return jsonify({'error': 'simulation_data.json not found'}), 404


@app.route('/dashboard_data.json')
def get_dashboard_data():
    study_name = "bike_rebalancing_study" # This should be dynamically determined if multiple studies exist
    scenario_name = "bike_rebalancing_sc_1" # This should also be dynamically determined
    
    # Construct the path to standard_eval.csv
    # FLEETPY_MAIN_DIR is e:\Sharing bike\FleetPy-main\FleetPy-main
    file_path = os.path.join(FLEETPY_MAIN_DIR, 'studies', study_name, 'results', scenario_name, 'standard_eval.csv')
    
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path, index_col=0)
            # Convert DataFrame to a dictionary. Use to_dict('index') to get a dict like {row_index: {col: val, ...}}
            # Or to_dict('list') to get {col: [val1, val2, ...]}
            # For KPI data, 'index' might be more suitable if index are KPI names.
            data = df.to_dict('index')
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': f'Error reading or parsing standard_eval.csv: {str(e)}'}), 500
    return jsonify({'error': 'standard_eval.csv not found'}), 404


@app.route('/resimulate', methods=['POST'])
def resimulate():
    global _current_preset_index
    try:
        # 切换到下一套预设
        _current_preset_index = (_current_preset_index + 1) % NUM_PRESETS
        preset_file = os.path.join(FLEETPY_MAIN_DIR, f'simulation_data_preset_{_current_preset_index}.json')
        target_file = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')

        if not os.path.exists(preset_file):
            return jsonify({'error': f'Preset file not found: {preset_file}'}), 500

        shutil.copy(preset_file, target_file)
        print(f'Switched to preset {_current_preset_index}')
        return jsonify({
            'message': f'已切换到预设方案 {_current_preset_index + 1}，单车重新分布完成！',
            'preset': _current_preset_index
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'切换预设失败: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)
