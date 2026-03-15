import os
import json
import random
import time
from datetime import datetime, timedelta
import logging

# Configure logging to file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("simulation_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Assuming fleetpy_utils.py is in the same directory or accessible via PYTHONPATH
from fleetpy_utils import FleetPyNetworkHelper

# --- Configuration ---
FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(FLEETPY_MAIN_DIR, "simulation_data.json")

# --- High-level simulation configuration ---
# 为了让动画更顺滑，我们缩短总时长并进一步加密时间步，这样蓝点更接近“连续移动”
SIMULATION_DURATION_MINUTES = 20  # 可视化 demo：20 分钟足够展示完整循环
TIME_STEP_SECONDS = 1  # 1 秒一帧，结合前端 120ms 播放间隔，基本看不出跳跃

# 无人车数量保持 3 个，方便肉眼追踪每一辆车的行为
NUM_VEHICLES = 3  # Number of unmanned vehicles (blue dots)
# 单车总数控制在二十来个即可
NUM_BIKES = 24  # Number of shared bikes (red dots)
# 绿点：停车站数量保持 3 个
NUM_PARKING_SPOTS = 3  # Number of parking spots/stations (green dots)

# --- Bike appearance configuration ---
# 初始就有一小部分“散落”的单车（红点）可见，避免一开始地图太空
INITIAL_ACTIVE_BIKES = 12  # 初始直接作为 misplaced 出现的红点数量

# 后续红点逐渐增加：每隔一段时间，从 inactive 里再激活 3～4 个
BIKE_APPEARANCE_INTERVAL_SECONDS = 90  # every 1.5 minutes introduce a few new bikes
MIN_BIKES_PER_INTERVAL = 3  # 每次至少激活 3 个
MAX_BIKES_PER_INTERVAL = 4  # 每次最多激活 4 个

# --- Helper Initialization ---
helper = FleetPyNetworkHelper(FLEETPY_MAIN_DIR)
all_nodes = list(helper.G.nodes)

# Get network center and bbox for initial map view
center_lat, center_lon = helper.get_network_center()
min_lat, max_lat, min_lon, max_lon = helper.get_network_bbox()

# --- Entity Initialization ---

# Initialize parking spots (stations)
parking_spots = []
random_parking_nodes = random.sample(all_nodes, NUM_PARKING_SPOTS)
for i, node_id in enumerate(random_parking_nodes):
    node_data = helper.G.nodes[node_id]
    parking_spots.append({
        "id": f"parking_{i}",
        "node_id": node_id,
        "lon": node_data['x'],
        "lat": node_data['y'],
    })

# Initialize bikes
all_bikes_state = {}  # {bike_id: "inactive" | "misplaced" | "on_vehicle" | "at_parking" | "on_vehicle_en_route"}
bikes = []
random_bike_nodes = random.sample(all_nodes, NUM_BIKES)
for i, node_id in enumerate(random_bike_nodes):
    node_data = helper.G.nodes[node_id]
    bike_id = f"bike_{i}"
    bikes.append({
        "id": bike_id,
        "node_id": node_id,
        "lon": node_data['x'],
        "lat": node_data['y'],
    })

# 初始：先把一部分单车直接设为“散落的红点”（misplaced），其余为 inactive，后续逐渐出现
initial_active_ids = set(random.sample([b["id"] for b in bikes], min(INITIAL_ACTIVE_BIKES, NUM_BIKES)))
for bike in bikes:
    if bike["id"] in initial_active_ids:
        all_bikes_state[bike["id"]] = "misplaced"
    else:
        all_bikes_state[bike["id"]] = "inactive"

# Initialize vehicles
vehicles = []
# 让车辆从停车站节点本身出发，避免总是在地图某个角落“刷出来”的感觉
vehicle_capacity = 3  # 每辆车一次可以虚拟“携带”最多 3 辆单车
for i in range(NUM_VEHICLES):
    # 如果停车站数量不足，就循环使用
    parking = parking_spots[i % len(parking_spots)]
    node_id = parking["node_id"]
    lon = parking["lon"]
    lat = parking["lat"]
    vehicles.append({
        "id": f"vehicle_{i}",
        "node_id": node_id,
        "lon": lon,
        "lat": lat,
        "current_task": None,  # "to_bike", "to_parking", "repositioning"
        "current_bike_id": None,  # ID of the bike being picked up or dropped off（当前正在前往的目标）
        "current_route_polyline": [],  # List of (lon, lat, cumulative_time) tuples
        "current_route_start_time": 0,  # Simulation time when the route started
        "current_route_total_time": 0,  # Total travel time for the current route
        "has_bike": False,  # 是否至少携带了一辆车
        "carried_bikes": 0,  # 当前已经装载的单车数量
        "capacity": vehicle_capacity,  # 最大装载数量
    })

# --- Simulation Logic ---

def assign_new_task(vehicle, current_sim_time):
    """
    Assigns a new task (pick up a bike or drop off a bike) to a vehicle.
    Prioritizes dropping off bikes if the vehicle has one, otherwise picks up a misplaced bike.
    The assignment is based on finding the shortest travel time to the target.
    """
    vehicle_node_id = vehicle["node_id"]
    
    # Task 1: Drop off bikes at a parking if the vehicle is "full" 或附近没有更多红点
    if vehicle["has_bike"] and vehicle.get("carried_bikes", 0) > 0:
        # 所有停车点都可以作为目标，我们在“最近的若干个”里随机挑一个，避免一直走同一条路
        candidate_parking_infos = []
        for parking in parking_spots:
            if parking["node_id"] == vehicle_node_id:
                continue  # already at this parking

            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, parking["node_id"])
            if route_polyline and route_polyline[-1][2] > 0:
                travel_time = route_polyline[-1][2]
                candidate_parking_infos.append((travel_time, parking, route_polyline))

        if candidate_parking_infos:
            # 先按时间排序，再从前 K 个里随机选一个
            candidate_parking_infos.sort(key=lambda x: x[0])
            K = min(2, len(candidate_parking_infos))  # 最近的前 2 个里随机
            chosen_travel_time, best_target_parking, best_route_polyline = random.choice(candidate_parking_infos[:K])

            vehicle["current_task"] = "to_parking"
            vehicle["current_bike_id"] = vehicle["current_bike_id"]  # Keep track of the bike
            vehicle["current_route_polyline"] = best_route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = chosen_travel_time
            logger.debug(
                f"Vehicle {vehicle['id']} assigned to drop off bike {vehicle['current_bike_id']} "
                f"at parking {best_target_parking['id']} (travel time: {chosen_travel_time:.2f}s)."
            )
            return True
        else:
            logger.debug(f"Vehicle {vehicle['id']} has bike but no valid route to any parking spots.")
            return False  # No valid place to drop off

    # Task 2: Pick up misplaced bikes if vehicle still has free capacity
    else:
        # 如果已经满载，则直接规划去停车场
        if vehicle.get("carried_bikes", 0) >= vehicle.get("capacity", 1):
            logger.debug(f"Vehicle {vehicle['id']} reached capacity, will go to parking next.")
            vehicle["has_bike"] = True
            return assign_new_task({**vehicle, "has_bike": True}, current_sim_time)

        eligible_misplaced_bike_ids = [bike_id for bike_id, status in all_bikes_state.items() if status == "misplaced"]

        candidate_bike_infos = []
        for bike_id in eligible_misplaced_bike_ids:
            target_bike_node_id = next(b["node_id"] for b in bikes if b["id"] == bike_id)

            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, target_bike_node_id)
            if route_polyline and route_polyline[-1][2] > 0:
                travel_time = route_polyline[-1][2]
                candidate_bike_infos.append((travel_time, bike_id, route_polyline))

        if candidate_bike_infos:
            # 同样：取最近的若干个里随机选，增加路径多样性
            candidate_bike_infos.sort(key=lambda x: x[0])
            K = min(3, len(candidate_bike_infos))  # 最近的前 3 个里随机
            chosen_travel_time, best_target_bike, best_route_polyline = random.choice(candidate_bike_infos[:K])

            vehicle["current_task"] = "to_bike"
            vehicle["current_bike_id"] = best_target_bike
            vehicle["current_route_polyline"] = best_route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = chosen_travel_time
            all_bikes_state[best_target_bike] = "on_vehicle_en_route"  # Mark bike as being picked up
            logger.debug(
                f"Vehicle {vehicle['id']} assigned to pick up bike {best_target_bike} "
                f"(travel time: {chosen_travel_time:.2f}s)."
            )
            return True
        else:
            logger.debug(f"Vehicle {vehicle['id']} has no bike and no available misplaced bikes with valid routes.")

            # Task 3: Reposition to a random parking spot if no misplaced bikes are available
            if not parking_spots:
                logger.debug(f"Vehicle {vehicle['id']} has no bike, no misplaced bikes, and no parking spots to reposition to.")
                return False  # No parking spots to reposition to

            target_parking_spot = random.choice(parking_spots)
            target_node_id = target_parking_spot["node_id"]

            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, target_node_id)
            if not route_polyline or route_polyline[-1][2] == 0:
                logger.debug(
                    f"Vehicle {vehicle['id']} (repositioning) - No valid route to random target parking {target_node_id}."
                )
                return False  # No valid route or zero travel time

            vehicle["current_task"] = "repositioning"
            vehicle["current_bike_id"] = None
            vehicle["current_route_polyline"] = route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = route_polyline[-1][2]
            logger.debug(
                f"Vehicle {vehicle['id']} assigned to reposition to parking "
                f"{target_parking_spot['id']} (travel time: {route_polyline[-1][2]:.2f}s)."
            )
            return True

# --- Simulation Loop ---
simulation_data = []
current_sim_time = 0 # seconds
last_bike_appearance_time = 0

while current_sim_time <= SIMULATION_DURATION_MINUTES * 60:
    # Dynamic bike appearance: 每隔一段时间，从 inactive 里激活少量红点，形成“渐进增多”的效果
    if current_sim_time > 0 and (current_sim_time - last_bike_appearance_time >= BIKE_APPEARANCE_INTERVAL_SECONDS):
        logger.debug(f"Attempting to activate bikes at {current_sim_time}s.")
        inactive_bikes = [bike_id for bike_id, status in all_bikes_state.items() if status == "inactive"]
        logger.debug(f"all_bikes_state at {current_sim_time}s: {all_bikes_state}")
        logger.debug(f"Found {len(inactive_bikes)} inactive bikes: {inactive_bikes}")
        if inactive_bikes:
            bikes_to_activate_count = random.randint(
                MIN_BIKES_PER_INTERVAL,
                MAX_BIKES_PER_INTERVAL
            )
            bikes_to_activate = random.sample(inactive_bikes, min(bikes_to_activate_count, len(inactive_bikes)))
            for bike_id in bikes_to_activate:
                all_bikes_state[bike_id] = "misplaced"
                logger.debug(f"Dynamically appeared bike {bike_id} at {current_sim_time}s.")
            last_bike_appearance_time = current_sim_time
    current_timestamp_data = {
        "time": current_sim_time,
        "vehicles": [],
        "bikes": [],
        "parking_spots": [],
    }

    # Update and record vehicle positions
    for veh in vehicles:
        current_lon, current_lat = veh["lon"], veh["lat"]

        if veh["current_task"]:
            elapsed_time_on_route = current_sim_time - veh["current_route_start_time"]
            
            if elapsed_time_on_route < veh["current_route_total_time"]:
                # Vehicle is still en route
                interpolated_lon, interpolated_lat = helper.get_interpolated_position(
                    veh["current_route_polyline"], elapsed_time_on_route
                )
                if interpolated_lon is not None and interpolated_lat is not None:
                    current_lon, current_lat = interpolated_lon, interpolated_lat
                else:
                    # Fallback if interpolation fails (shouldn't happen with proper polyline)
                    print(f"Warning: Interpolation failed for vehicle {veh['id']}. Using last known position.")
                    # Keep previous lon/lat
            else:
                # Vehicle arrived at destination
                destination_lon, destination_lat, _ = veh["current_route_polyline"][-1]
                current_lon, current_lat = destination_lon, destination_lat
                veh["node_id"] = helper.lon_lat_to_node_id(destination_lon, destination_lat)

                # Process task completion
                if veh["current_task"] == "to_bike":
                    bike_id_to_pickup = veh["current_bike_id"]
                    if bike_id_to_pickup and all_bikes_state.get(bike_id_to_pickup) == "on_vehicle_en_route":
                        veh["has_bike"] = True
                        # 增加车上携带的数量，模拟“一路多捡几辆”
                        veh["carried_bikes"] = veh.get("carried_bikes", 0) + 1
                        all_bikes_state[bike_id_to_pickup] = "on_vehicle"
                        # Bike is now on vehicle, it will not appear as a separate red dot
                    veh["current_task"] = None
                    veh["current_route_polyline"] = []
                    veh["current_route_start_time"] = 0
                    veh["current_route_total_time"] = 0
                
                elif veh["current_task"] == "to_parking":
                    bike_id_to_dropoff = veh["current_bike_id"]
                    if bike_id_to_dropoff and all_bikes_state.get(bike_id_to_dropoff) == "on_vehicle":
                        veh["has_bike"] = False
                        # 清空载货数，表示这一趟已经全部卸完
                        veh["carried_bikes"] = 0
                        all_bikes_state[bike_id_to_dropoff] = "at_parking"
                        # Update bike's position to parking spot
                        for b in bikes:
                            if b["id"] == bike_id_to_dropoff:
                                b["lon"] = current_lon
                                b["lat"] = current_lat
                                b["node_id"] = veh["node_id"]
                                break
                    veh["current_task"] = None
                    veh["current_bike_id"] = None

                elif veh["current_task"] == "repositioning":
                    veh["current_task"] = None
                    veh["current_bike_id"] = None
                
                # Assign a new task immediately upon arrival
                assign_new_task(veh, current_sim_time)
        else:
            # If no current task, try to assign one
            assign_new_task(veh, current_sim_time)

        # Update vehicle's current position for the record
        veh["lon"] = current_lon
        veh["lat"] = current_lat

        current_timestamp_data["vehicles"].append({
            "id": veh["id"],
            "lon": veh["lon"],
            "lat": veh["lat"],
            "has_bike": veh["has_bike"]
        })
    
    # Record bike positions
    for bike in bikes:
        # A bike is rendered if it's misplaced, at_parking, or en route to be picked up
        # A bike is NOT rendered if its state is "on_vehicle"
        if all_bikes_state.get(bike["id"]) in ["misplaced", "at_parking", "on_vehicle_en_route"]:
            current_timestamp_data["bikes"].append({
                "id": bike["id"],
                "lon": bike["lon"],
                "lat": bike["lat"],
                "status": all_bikes_state[bike["id"]]
            })
    
    # Record parking spot positions
    for ps in parking_spots:
        current_timestamp_data["parking_spots"].append({
            "id": ps["id"],
            "lon": ps["lon"],
            "lat": ps["lat"],
        })

    simulation_data.append(current_timestamp_data)
    current_sim_time += TIME_STEP_SECONDS

# Save simulation data to JSON
final_output_data = {
    "frames": simulation_data,
    "total_duration": SIMULATION_DURATION_MINUTES * 60, # Adding total duration
    "initial_map_view": {
        "center": [center_lat, center_lon],
        "bbox": [min_lat, max_lat, min_lon, max_lon]
    }
}
with open(OUTPUT_FILE, "w") as f:
    json.dump(final_output_data, f, indent=4)

logger.info(f"Simulation data generated and saved to {OUTPUT_FILE}")
