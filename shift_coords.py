import json

with open(r'E:\Sharing bike\FleetPy-main\FleetPy-main\simulation_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 慕尼黑中心坐标
origin_lat = 48.095
origin_lon = 11.64
# 目标：成都市中心
target_lat = 30.65
target_lon = 104.07

dlat = target_lat - origin_lat
dlon = target_lon - origin_lon

for frame in data['frames']:
    for v in frame.get('vehicles', []):
        v['lat'] += dlat
        v['lon'] += dlon
        if 'route_lonlats' in v:
            v['route_lonlats'] = [[p[0]+dlon, p[1]+dlat] for p in v['route_lonlats']]
    for b in frame.get('bikes', []):
        b['lat'] += dlat
        b['lon'] += dlon
    for s in frame.get('parking_spots', []):
        s['lat'] += dlat
        s['lon'] += dlon
    for s in frame.get('stations', []):
        s['lat'] += dlat
        s['lon'] += dlon

# 更新 initial_map_view
if 'initial_map_view' in data:
    if 'center' in data['initial_map_view']:
        data['initial_map_view']['center'][0] += dlat
        data['initial_map_view']['center'][1] += dlon
    if 'bbox' in data['initial_map_view']:
        bb = data['initial_map_view']['bbox']
        data['initial_map_view']['bbox'] = [bb[0]+dlat, bb[1]+dlat, bb[2]+dlon, bb[3]+dlon]

with open(r'E:\Sharing bike\FleetPy-main\FleetPy-main\simulation_data.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('Done! New center:', data['initial_map_view']['center'])
