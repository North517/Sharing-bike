import json
import requests
import time
import math
import random

AMAP_KEY = 'fe48c16fd360355b2a506c6ab7c91f5e'

# 山西农业大学太谷校区内部坐标（实测校内位置）
# 学校大门在 112.5838, 37.4240 附近，校区偏东侧
# 以下坐标均在校区内部道路附近

# 校内停车站点（3个，分布在校内各区域）
PARKING_SPOTS = [
    {'id': 'parking_0', 'lon': 112.5812, 'lat': 37.4255, 'name': '北区站点'},
    {'id': 'parking_1', 'lon': 112.5848, 'lat': 37.4238, 'name': '中区站点'},
    {'id': 'parking_2', 'lon': 112.5832, 'lat': 37.4220, 'name': '南区站点'},
]

# 校内散落单车位置（25辆，分布在校内各处）
BIKE_POSITIONS = [
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
]

NUM_FRAMES = 601
COLLECT_RADIUS = 0.0003  # 约30米，无人车进入此范围单车消失

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
                polyline = step.get('polyline', '')
                for point in polyline.split(';'):
                    parts = point.split(',')
                    if len(parts) == 2:
                        try:
                            lon = float(parts[0])
                            lat = float(parts[1])
                            if not coords or coords[-1] != [lon, lat]:
                                coords.append([lon, lat])
                        except:
                            pass
            if coords:
                return coords
        else:
            print(f'  API: {data.get("info")} ({data.get("infocode")})')
    except Exception as e:
        print(f'  API error: {e}')
    return [[origin_lon, origin_lat], [dest_lon, dest_lat]]


def dist(a_lon, a_lat, b_lon, b_lat):
    return math.sqrt((a_lon-b_lon)**2 + (a_lat-b_lat)**2)


def interpolate_route(route_coords, num_steps):
    """将路径插值为 num_steps 个点"""
    if len(route_coords) < 2:
        return [route_coords[0]] * num_steps
    seg_lengths = []
    total_len = 0
    for i in range(len(route_coords)-1):
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


def plan_vehicle_mission(start_parking, bikes, home_parking):
    """
    规划无人车任务：从起始站出发，按最近距离依次收集单车，最后回到停车站
    返回: 任务段列表 [{'type':'goto_bike'/'return', 'route':[...], 'collect_bike_id': id or None}]
    """
    missions = []
    current_lon = start_parking['lon']
    current_lat = start_parking['lat']
    remaining_bikes = list(bikes)  # copy

    while remaining_bikes:
        # 找最近的单车
        nearest = min(remaining_bikes,
                      key=lambda b: dist(current_lon, current_lat, b['lon'], b['lat']))
        print(f'    -> collecting {nearest["id"]} at ({nearest["lat"]:.4f},{nearest["lon"]:.4f})')
        route = get_road_route(current_lon, current_lat, nearest['lon'], nearest['lat'])
        time.sleep(0.2)
        missions.append({
            'type': 'goto_bike',
            'route': route,
            'collect_bike_id': nearest['id'],
            'dest_lon': nearest['lon'],
            'dest_lat': nearest['lat']
        })
        current_lon = nearest['lon']
        current_lat = nearest['lat']
        remaining_bikes.remove(nearest)

    # 回到停车站
    print(f'    -> returning to {home_parking["id"]}')
    route = get_road_route(current_lon, current_lat, home_parking['lon'], home_parking['lat'])
    time.sleep(0.2)
    missions.append({
        'type': 'return',
        'route': route,
        'collect_bike_id': None,
        'dest_lon': home_parking['lon'],
        'dest_lat': home_parking['lat']
    })
    return missions


# 将3辆车的单车平均分配
random.seed(42)
bikes_copy = list(BIKE_POSITIONS)
random.shuffle(bikes_copy)
v0_bikes = bikes_copy[0:9]
v1_bikes = bikes_copy[9:17]
v2_bikes = bikes_copy[17:25]

print('Planning missions for 3 vehicles...')
print('Vehicle 0 collecting', len(v0_bikes), 'bikes')
vehicle_0_missions = plan_vehicle_mission(PARKING_SPOTS[0], v0_bikes, PARKING_SPOTS[0])
print('Vehicle 1 collecting', len(v1_bikes), 'bikes')
vehicle_1_missions = plan_vehicle_mission(PARKING_SPOTS[1], v1_bikes, PARKING_SPOTS[1])
print('Vehicle 2 collecting', len(v2_bikes), 'bikes')
vehicle_2_missions = plan_vehicle_mission(PARKING_SPOTS[2], v2_bikes, PARKING_SPOTS[2])

all_vehicle_missions = [
    {'id': 'vehicle_0', 'missions': vehicle_0_missions, 'parking': PARKING_SPOTS[0]},
    {'id': 'vehicle_1', 'missions': vehicle_1_missions, 'parking': PARKING_SPOTS[1]},
    {'id': 'vehicle_2', 'missions': vehicle_2_missions, 'parking': PARKING_SPOTS[2]},
]


def expand_missions_to_frames(vehicle_missions_list, num_frames):
    """
    将所有车辆任务展开为逐帧数据
    返回:
      vehicle_positions[frame_idx][vid] = [lon, lat]
      collected_by_frame[frame_idx] = set of collected bike ids
    """
    # 计算总路程段数（所有车辆所有任务的路径点总数）
    # 每辆车的任务按比例分配帧数
    vehicle_frame_data = {}  # vid -> list of (lon, lat) per frame
    vehicle_collected = {}   # vid -> list of (frame_idx, bike_id) when collected

    for vm in vehicle_missions_list:
        vid = vm['id']
        missions = vm['missions']

        # 计算总路径长度
        total_dist = 0
        for m in missions:
            r = m['route']
            for i in range(len(r)-1):
                total_dist += dist(r[i][0], r[i][1], r[i+1][0], r[i+1][1])

        # 按距离比例分配帧数给每段任务
        positions = []
        collected_events = []
        accumulated_frames = 0

        for m_idx, m in enumerate(missions):
            route = m['route']
            # 计算该段距离
            seg_dist = sum(
                dist(route[i][0], route[i][1], route[i+1][0], route[i+1][1])
                for i in range(len(route)-1)
            )
            if total_dist > 0:
                seg_frames = max(2, int((seg_dist / total_dist) * num_frames))
            else:
                seg_frames = 2

            # 最后一段补齐剩余帧数
            if m_idx == len(missions) - 1:
                seg_frames = num_frames - len(positions)
                if seg_frames < 2:
                    seg_frames = 2

            seg_positions = interpolate_route(route, seg_frames)
            start_frame = len(positions)
            positions.extend(seg_positions)

            # 记录收集事件（到达终点时）
            if m['collect_bike_id']:
                collect_frame = start_frame + seg_frames - 1
                collected_events.append((collect_frame, m['collect_bike_id']))

        # 截断或补齐到 num_frames
        if len(positions) > num_frames:
            positions = positions[:num_frames]
        while len(positions) < num_frames:
            positions.append(positions[-1])

        vehicle_frame_data[vid] = positions
        vehicle_collected[vid] = collected_events

    return vehicle_frame_data, vehicle_collected


print('\nExpanding missions to frames...')
vehicle_frame_data, vehicle_collected = expand_missions_to_frames(
    all_vehicle_missions, NUM_FRAMES
)

# 构建每辆车已收集单车的帧索引集合
# collected_at[bike_id] = frame_idx when collected
collected_at = {}
for vm in all_vehicle_missions:
    vid = vm['id']
    for (frame_idx, bike_id) in vehicle_collected[vid]:
        collected_at[bike_id] = frame_idx

print('Collected events:', collected_at)

print('Generating frames...')
frames = []
for fi in range(NUM_FRAMES):
    vehicles = []
    for vm in all_vehicle_missions:
        vid = vm['id']
        pos = vehicle_frame_data[vid][fi]
        # 判断当前是否携带单车（正在去收集途中且已收集过至少一辆）
        collected_count = sum(1 for (f, _) in vehicle_collected[vid] if f <= fi)
        vehicles.append({
            'id': vid,
            'lon': pos[0],
            'lat': pos[1],
            'has_bike': collected_count > 0
        })

    # 单车：未被收集的显示，已收集的消失
    bikes = []
    for bike in BIKE_POSITIONS:
        bid = bike['id']
        if bid not in collected_at or fi < collected_at[bid]:
            bikes.append({
                'id': bid,
                'lon': bike['lon'],
                'lat': bike['lat'],
                'status': 'misplaced'
            })

    parking_spots = [{
        'id': p['id'],
        'lon': p['lon'],
        'lat': p['lat']
    } for p in PARKING_SPOTS]

    frames.append({
        'time': fi,
        'vehicles': vehicles,
        'bikes': bikes,
        'parking_spots': parking_spots
    })

# BBox
all_lons = [b['lon'] for b in BIKE_POSITIONS] + [p['lon'] for p in PARKING_SPOTS]
all_lats = [b['lat'] for b in BIKE_POSITIONS] + [p['lat'] for p in PARKING_SPOTS]
min_lon = min(all_lons) - 0.003
max_lon = max(all_lons) + 0.003
min_lat = min(all_lats) - 0.003
max_lat = max(all_lats) + 0.003
center_lon = (min_lon + max_lon) / 2
center_lat = (min_lat + max_lat) / 2

data = {
    'frames': frames,
    'total_duration': 600,
    'initial_map_view': {
        'center': [center_lat, center_lon],
        'bbox': [min_lat, max_lat, min_lon, max_lon]
    }
}

print('Saving simulation_data.json...')
with open(r'E:\Sharing bike\FleetPy-main\FleetPy-main\simulation_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'Done!')
print(f'Total frames: {NUM_FRAMES}')
print(f'Bikes placed: {len(BIKE_POSITIONS)}')
print(f'Bikes collected: {len(collected_at)}')
