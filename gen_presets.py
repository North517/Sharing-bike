import json
import requests
import time
import math
import random
import os

AMAP_KEY = 'fe48c16fd360355b2a506c6ab7c91f5e'

PARKING_SPOTS = [
    {'id': 'parking_0', 'lon': 112.5812, 'lat': 37.4255, 'name': '北区站点'},
    {'id': 'parking_1', 'lon': 112.5848, 'lat': 37.4238, 'name': '中区站点'},
    {'id': 'parking_2', 'lon': 112.5832, 'lat': 37.4220, 'name': '南区站点'},
]

PRESET_BIKES = [
    # 套装0：均匀分布
    [
        {'id': 'bike_0',  'lon': 112.5820, 'lat': 37.4260},
        {'id': 'bike_1',  'lon': 112.5835, 'lat': 37.4265},
        {'id': 'bike_2',  'lon': 112.5855, 'lat': 37.4258},
        {'id': 'bike_3',  'lon': 112.5862, 'lat': 37.4245},
        {'id': 'bike_4',  'lon': 112.5858, 'lat': 37.4232},
        {'id': 'bike_5',  'lon': 112.5845, 'lat': 37.4225},
        {'id': 'bike_6',  'lon': 112.5828, 'lat': 37.4228},
        {'id': 'bike_7',  'lon': 112.5818, 'lat': 37.4238},
        {'id': 'bike_8',  'lon': 112.5822, 'lat': 37.4248},
        {'id': 'bike_9',  'lon': 112.5840, 'lat': 37.4250},
        {'id': 'bike_10', 'lon': 112.5852, 'lat': 37.4252},
        {'id': 'bike_11', 'lon': 112.5865, 'lat': 37.4260},
        {'id': 'bike_12', 'lon': 112.5870, 'lat': 37.4242},
        {'id': 'bike_13', 'lon': 112.5860, 'lat': 37.4220},
        {'id': 'bike_14', 'lon': 112.5840, 'lat': 37.4215},
        {'id': 'bike_15', 'lon': 112.5820, 'lat': 37.4218},
        {'id': 'bike_16', 'lon': 112.5810, 'lat': 37.4230},
        {'id': 'bike_17', 'lon': 112.5808, 'lat': 37.4248},
        {'id': 'bike_18', 'lon': 112.5825, 'lat': 37.4235},
        {'id': 'bike_19', 'lon': 112.5843, 'lat': 37.4242},
        {'id': 'bike_20', 'lon': 112.5856, 'lat': 37.4236},
        {'id': 'bike_21', 'lon': 112.5832, 'lat': 37.4244},
        {'id': 'bike_22', 'lon': 112.5815, 'lat': 37.4255},
        {'id': 'bike_23', 'lon': 112.5848, 'lat': 37.4262},
        {'id': 'bike_24', 'lon': 112.5838, 'lat': 37.4228},
    ],
    # 套装1：偏北侧集中
    [
        {'id': 'bike_0',  'lon': 112.5808, 'lat': 37.4268},
        {'id': 'bike_1',  'lon': 112.5818, 'lat': 37.4272},
        {'id': 'bike_2',  'lon': 112.5830, 'lat': 37.4270},
        {'id': 'bike_3',  'lon': 112.5842, 'lat': 37.4268},
        {'id': 'bike_4',  'lon': 112.5855, 'lat': 37.4265},
        {'id': 'bike_5',  'lon': 112.5865, 'lat': 37.4260},
        {'id': 'bike_6',  'lon': 112.5870, 'lat': 37.4252},
        {'id': 'bike_7',  'lon': 112.5868, 'lat': 37.4242},
        {'id': 'bike_8',  'lon': 112.5815, 'lat': 37.4262},
        {'id': 'bike_9',  'lon': 112.5825, 'lat': 37.4258},
        {'id': 'bike_10', 'lon': 112.5838, 'lat': 37.4255},
        {'id': 'bike_11', 'lon': 112.5850, 'lat': 37.4255},
        {'id': 'bike_12', 'lon': 112.5860, 'lat': 37.4248},
        {'id': 'bike_13', 'lon': 112.5835, 'lat': 37.4248},
        {'id': 'bike_14', 'lon': 112.5845, 'lat': 37.4245},
        {'id': 'bike_15', 'lon': 112.5820, 'lat': 37.4252},
        {'id': 'bike_16', 'lon': 112.5810, 'lat': 37.4258},
        {'id': 'bike_17', 'lon': 112.5805, 'lat': 37.4248},
        {'id': 'bike_18', 'lon': 112.5828, 'lat': 37.4262},
        {'id': 'bike_19', 'lon': 112.5858, 'lat': 37.4238},
        {'id': 'bike_20', 'lon': 112.5872, 'lat': 37.4245},
        {'id': 'bike_21', 'lon': 112.5862, 'lat': 37.4232},
        {'id': 'bike_22', 'lon': 112.5832, 'lat': 37.4240},
        {'id': 'bike_23', 'lon': 112.5842, 'lat': 37.4260},
        {'id': 'bike_24', 'lon': 112.5852, 'lat': 37.4262},
    ],
    # 套装2：偏南侧分散
    [
        {'id': 'bike_0',  'lon': 112.5808, 'lat': 37.4222},
        {'id': 'bike_1',  'lon': 112.5818, 'lat': 37.4218},
        {'id': 'bike_2',  'lon': 112.5830, 'lat': 37.4215},
        {'id': 'bike_3',  'lon': 112.5845, 'lat': 37.4212},
        {'id': 'bike_4',  'lon': 112.5858, 'lat': 37.4215},
        {'id': 'bike_5',  'lon': 112.5868, 'lat': 37.4222},
        {'id': 'bike_6',  'lon': 112.5872, 'lat': 37.4232},
        {'id': 'bike_7',  'lon': 112.5865, 'lat': 37.4240},
        {'id': 'bike_8',  'lon': 112.5810, 'lat': 37.4232},
        {'id': 'bike_9',  'lon': 112.5822, 'lat': 37.4225},
        {'id': 'bike_10', 'lon': 112.5835, 'lat': 37.4222},
        {'id': 'bike_11', 'lon': 112.5848, 'lat': 37.4218},
        {'id': 'bike_12', 'lon': 112.5860, 'lat': 37.4228},
        {'id': 'bike_13', 'lon': 112.5838, 'lat': 37.4230},
        {'id': 'bike_14', 'lon': 112.5825, 'lat': 37.4235},
        {'id': 'bike_15', 'lon': 112.5812, 'lat': 37.4242},
        {'id': 'bike_16', 'lon': 112.5805, 'lat': 37.4235},
        {'id': 'bike_17', 'lon': 112.5820, 'lat': 37.4228},
        {'id': 'bike_18', 'lon': 112.5842, 'lat': 37.4225},
        {'id': 'bike_19', 'lon': 112.5855, 'lat': 37.4232},
        {'id': 'bike_20', 'lon': 112.5868, 'lat': 37.4238},
        {'id': 'bike_21', 'lon': 112.5858, 'lat': 37.4245},
        {'id': 'bike_22', 'lon': 112.5832, 'lat': 37.4218},
        {'id': 'bike_23', 'lon': 112.5815, 'lat': 37.4225},
        {'id': 'bike_24', 'lon': 112.5845, 'lat': 37.4235},
    ],
]

NUM_FRAMES = 601
OUTPUT_DIR = r'E:\Sharing bike\FleetPy-main\FleetPy-main'


def get_road_route(origin_lon, origin_lat, dest_lon, dest_lat):
    url = 'https://restapi.amap.com/v3/direction/driving'
    params = {
        'key': AMAP_KEY,
        'origin': f'{origin_lon:.6f},{origin_lat:.6f}',
        'destination': f'{dest_lon:.6f},{dest_lat:.6f}',
        'output': 'json',
        'extensions': 'base'
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get('status') == '1' and data.get('route'):
            steps = data['route']['paths'][0]['steps']
            coords = []
            for step in steps:
                for point in step.get('polyline', '').split(';'):
                    parts = point.split(',')
                    if len(parts) == 2:
                        try:
                            lon, lat = float(parts[0]), float(parts[1])
                            if not coords or coords[-1] != [lon, lat]:
                                coords.append([lon, lat])
                        except:
                            pass
            if coords:
                return coords
    except Exception as e:
        print(f'  API error: {e}')
    return [[origin_lon, origin_lat], [dest_lon, dest_lat]]


def dist(a_lon, a_lat, b_lon, b_lat):
    return math.sqrt((a_lon - b_lon) ** 2 + (a_lat - b_lat) ** 2)


def interpolate_route(route_coords, num_steps):
    if len(route_coords) < 2:
        return [route_coords[0]] * num_steps
    seg_lengths = []
    total_len = 0
    for i in range(len(route_coords) - 1):
        d = dist(route_coords[i][0], route_coords[i][1],
                 route_coords[i+1][0], route_coords[i+1][1])
        seg_lengths.append(d)
        total_len += d
    if total_len == 0:
        return [route_coords[0]] * num_steps
    result = []
    for f in range(num_steps):
        t = f / max(num_steps - 1, 1)
        target = t * total_len
        acc = 0
        placed = False
        for i, sl in enumerate(seg_lengths):
            if acc + sl >= target:
                ratio = (target - acc) / sl if sl > 0 else 0
                lon = route_coords[i][0] + ratio * (route_coords[i+1][0] - route_coords[i][0])
                lat = route_coords[i][1] + ratio * (route_coords[i+1][1] - route_coords[i][1])
                result.append([lon, lat])
                placed = True
                break
            acc += sl
        if not placed:
            result.append(route_coords[-1])
    return result


def plan_and_generate(bike_positions, preset_idx):
    bikes_copy = list(bike_positions)
    random.seed(preset_idx * 7 + 13)
    random.shuffle(bikes_copy)
    v_bikes = [bikes_copy[0:9], bikes_copy[9:17], bikes_copy[17:25]]

    def plan_mission(start_lon, start_lat, bikes, home):
        missions = []
        cur_lon, cur_lat = start_lon, start_lat
        remaining = list(bikes)
        while remaining:
            nearest = min(remaining, key=lambda b: dist(cur_lon, cur_lat, b['lon'], b['lat']))
            route = get_road_route(cur_lon, cur_lat, nearest['lon'], nearest['lat'])
            time.sleep(0.15)
            missions.append({'type': 'goto_bike', 'route': route,
                             'collect_bike_id': nearest['id']})
            cur_lon, cur_lat = nearest['lon'], nearest['lat']
            remaining.remove(nearest)
        route = get_road_route(cur_lon, cur_lat, home['lon'], home['lat'])
        time.sleep(0.15)
        missions.append({'type': 'return', 'route': route, 'collect_bike_id': None})
        return missions

    all_missions = []
    for i in range(3):
        p = PARKING_SPOTS[i]
        print(f'  vehicle_{i}: routing {len(v_bikes[i])} bikes...')
        missions = plan_mission(p['lon'], p['lat'], v_bikes[i], p)
        all_missions.append({'id': f'vehicle_{i}', 'missions': missions})

    vehicle_frame_data = {}
    vehicle_collected = {}
    for vm in all_missions:
        vid = vm['id']
        missions = vm['missions']
        total_dist = sum(
            dist(r[i][0], r[i][1], r[i+1][0], r[i+1][1])
            for m in missions for r in [m['route']]
            for i in range(len(r) - 1)
        )
        positions = []
        collected_events = []
        for m_idx, m in enumerate(missions):
            route = m['route']
            seg_dist = sum(dist(route[i][0], route[i][1], route[i+1][0], route[i+1][1])
                          for i in range(len(route) - 1))
            seg_frames = max(2, int((seg_dist / total_dist) * NUM_FRAMES)) if total_dist > 0 else 2
            if m_idx == len(missions) - 1:
                seg_frames = max(2, NUM_FRAMES - len(positions))
            start_f = len(positions)
            positions.extend(interpolate_route(route, seg_frames))
            if m['collect_bike_id']:
                collected_events.append((start_f + seg_frames - 1, m['collect_bike_id']))
        positions = positions[:NUM_FRAMES]
        while len(positions) < NUM_FRAMES:
            positions.append(positions[-1])
        vehicle_frame_data[vid] = positions
        vehicle_collected[vid] = collected_events

    collected_at = {}
    for vm in all_missions:
        for (frame_idx, bike_id) in vehicle_collected[vm['id']]:
            collected_at[bike_id] = frame_idx

    frames = []
    for fi in range(NUM_FRAMES):
        vehicles = []
        for vm in all_missions:
            vid = vm['id']
            pos = vehicle_frame_data[vid][fi]
            cnt = sum(1 for (f, _) in vehicle_collected[vid] if f <= fi)
            vehicles.append({'id': vid, 'lon': pos[0], 'lat': pos[1], 'has_bike': cnt > 0})
        bikes = []
        for bike in bike_positions:
            if bike['id'] not in collected_at or fi < collected_at[bike['id']]:
                bikes.append({'id': bike['id'], 'lon': bike['lon'],
                             'lat': bike['lat'], 'status': 'misplaced'})
        frames.append({
            'time': fi,
            'vehicles': vehicles,
            'bikes': bikes,
            'parking_spots': [{'id': p['id'], 'lon': p['lon'], 'lat': p['lat']}
                              for p in PARKING_SPOTS]
        })

    all_lons = [b['lon'] for b in bike_positions] + [p['lon'] for p in PARKING_SPOTS]
    all_lats = [b['lat'] for b in bike_positions] + [p['lat'] for p in PARKING_SPOTS]
    return {
        'frames': frames,
        'total_duration': 600,
        'initial_map_view': {
            'center': [sum(all_lats)/len(all_lats), sum(all_lons)/len(all_lons)],
            'bbox': [min(all_lats)-0.003, max(all_lats)+0.003,
                     min(all_lons)-0.003, max(all_lons)+0.003]
        }
    }


for idx, bikes in enumerate(PRESET_BIKES):
    print(f'\n=== Generating preset {idx} ===')
    data = plan_and_generate(bikes, idx)
    out_path = os.path.join(OUTPUT_DIR, f'simulation_data_preset_{idx}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  Saved: {out_path}')
    print(f'  Bikes collected: {sum(1 for frame in data["frames"][-1:] for _ in [None]) and len([b for b in PRESET_BIKES[idx] if True])}')

print('\nAll presets generated!')
