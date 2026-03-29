import json
import requests
import time
import math

AMAP_KEY = 'fe48c16fd360355b2a506c6ab7c91f5e'

def get_road_route(origin_lon, origin_lat, dest_lon, dest_lat):
    """调用高德驾车路线规划API，返回路径坐标列表 [[lon, lat], ...]"""
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
                            # 去重相邻重复点
                            if not coords or coords[-1] != [lon, lat]:
                                coords.append([lon, lat])
                        except:
                            pass
            if coords:
                print(f'  Got {len(coords)} road waypoints')
                return coords
        else:
            print(f'  API returned: {data.get("info")} ({data.get("infocode")})')
    except Exception as e:
        print(f'  API error: {e}')
    # 失败则返回直线两点
    print('  Falling back to straight line')
    return [[origin_lon, origin_lat], [dest_lon, dest_lat]]


def dist(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)


def interpolate_along_route(route_coords, num_frames):
    """将路径坐标插值为 num_frames 个均匀分布的点"""
    if len(route_coords) < 2:
        return [route_coords[0]] * num_frames

    # 计算各段长度和总长度
    seg_lengths = []
    total_len = 0
    for i in range(len(route_coords)-1):
        d = dist(route_coords[i], route_coords[i+1])
        seg_lengths.append(d)
        total_len += d

    if total_len == 0:
        return [route_coords[0]] * num_frames

    result = []
    for f in range(num_frames):
        t = f / max(num_frames - 1, 1)  # 0.0 ~ 1.0
        target_len = t * total_len
        accumulated = 0
        placed = False
        for i, seg_len in enumerate(seg_lengths):
            if accumulated + seg_len >= target_len:
                if seg_len == 0:
                    result.append(route_coords[i])
                else:
                    ratio = (target_len - accumulated) / seg_len
                    lon = route_coords[i][0] + ratio * (route_coords[i+1][0] - route_coords[i][0])
                    lat = route_coords[i][1] + ratio * (route_coords[i+1][1] - route_coords[i][1])
                    result.append([lon, lat])
                placed = True
                break
            accumulated += seg_len
        if not placed:
            result.append(route_coords[-1])

    return result


print('Loading simulation_data.json...')
with open(r'E:\Sharing bike\FleetPy-main\FleetPy-main\simulation_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

frames = data['frames']
num_frames = len(frames)

# 收集每辆车所有帧的起点和终点
vehicle_ids = list({v['id'] for frame in frames for v in frame['vehicles']})
print(f'Total frames: {num_frames}, Vehicles: {vehicle_ids}')

for vid in vehicle_ids:
    # 找该车出现的第一帧和最后一帧
    first_frame = None
    last_frame = None
    for frame in frames:
        for v in frame['vehicles']:
            if v['id'] == vid:
                if first_frame is None:
                    first_frame = (frame['time'], v['lon'], v['lat'])
                last_frame = (frame['time'], v['lon'], v['lat'])

    if not first_frame or not last_frame:
        continue

    origin_lon, origin_lat = first_frame[1], first_frame[2]
    dest_lon, dest_lat = last_frame[1], last_frame[2]

    print(f'\nRouting {vid}: ({origin_lat:.4f},{origin_lon:.4f}) -> ({dest_lat:.4f},{dest_lon:.4f})')

    # 如果起终点太近（<0.0001度≈10m），跳过
    if dist([origin_lon, origin_lat], [dest_lon, dest_lat]) < 0.0001:
        print(f'  Start and end too close, skipping routing')
        continue

    route_coords = get_road_route(origin_lon, origin_lat, dest_lon, dest_lat)
    time.sleep(0.5)  # 避免频繁调用

    # 找该车出现的帧范围
    vehicle_frames = []
    for i, frame in enumerate(frames):
        for v in frame['vehicles']:
            if v['id'] == vid:
                vehicle_frames.append(i)
                break

    num_vehicle_frames = len(vehicle_frames)
    interpolated = interpolate_along_route(route_coords, num_vehicle_frames)

    # 更新每帧中该车辆的坐标
    for idx, frame_idx in enumerate(vehicle_frames):
        for v in frames[frame_idx]['vehicles']:
            if v['id'] == vid:
                v['lon'] = interpolated[idx][0]
                v['lat'] = interpolated[idx][1]
                break

print('\nSaving updated simulation_data.json...')
with open(r'E:\Sharing bike\FleetPy-main\FleetPy-main\simulation_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('Done! Vehicles now follow real road routes.')
