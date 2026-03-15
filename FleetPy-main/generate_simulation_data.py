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

SIMULATION_DURATION_MINUTES = 60 # Total simulation time
TIME_STEP_SECONDS = 5 # How often to record data points for visualization
NUM_VEHICLES = 3 # Number of unmanned vehicles (blue dots)
NUM_BIKES = 20 # Number of shared bikes (red dots)
NUM_PARKING_SPOTS = 3 # Number of parking spots/stations (green dots)
BIKE_APPEARANCE_INTERVAL_SECONDS = 180 # Every 3 minutes, new bikes might appear more frequently
BIKES_PER_INTERVAL = 5 # Number of bikes to make misplaced per interval (increased for more activity)

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
all_bikes_state = {} # {bike_id: "misplaced" | "on_vehicle" | "at_parking"}
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
    all_bikes_state[bike_id] = "inactive" # Bikes start as inactive, appear dynamically

# Initialize vehicles
vehicles = []
random_vehicle_nodes = random.sample(all_nodes, NUM_VEHICLES)
for i, node_id in enumerate(random_vehicle_nodes):
    node_data = helper.G.nodes[node_id]
    vehicles.append({
        "id": f"vehicle_{i}",
        "node_id": node_id,
        "lon": node_data['x'],
        "lat": node_data['y'],
        "current_task": None, # "to_bike", "to_parking"
        "current_bike_id": None, # ID of the bike being picked up or dropped off
        "current_route_polyline": [], # List of (lon, lat, cumulative_time) tuples
        "current_route_start_time": 0, # Simulation time when the route started
        "current_route_total_time": 0, # Total travel time for the current route
        "has_bike": False, # True if vehicle is carrying a bike
    })

# --- Simulation Logic ---

def assign_new_task(vehicle, current_sim_time):
    """
    Assigns a new task (pick up a bike or drop off a bike) to a vehicle.
    Prioritizes dropping off bikes if the vehicle has one, otherwise picks up a misplaced bike.
    The assignment is based on finding the shortest travel time to the target.
    """
    vehicle_node_id = vehicle["node_id"]
    
    # Task 1: Drop off a bike if the vehicle has one
    if vehicle["has_bike"]:
        best_target_parking = None
        min_travel_time = float('inf')

        for parking in parking_spots:
            if parking["node_id"] == vehicle_node_id:
                continue # Cannot drop off at current location if already there
            
            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, parking["node_id"])
            if route_polyline and route_polyline[-1][2] > 0:
                travel_time = route_polyline[-1][2]
                if travel_time < min_travel_time:
                    min_travel_time = travel_time
                    best_target_parking = parking
                    best_route_polyline = route_polyline

        if best_target_parking:
            vehicle["current_task"] = "to_parking"
            vehicle["current_bike_id"] = vehicle["current_bike_id"] # Keep track of the bike
            vehicle["current_route_polyline"] = best_route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = min_travel_time
            logger.debug(f"Vehicle {vehicle['id']} assigned to drop off bike {vehicle['current_bike_id']} at parking {best_target_parking['id']} (travel time: {min_travel_time:.2f}s).")
            return True
        else:
            logger.debug(f"Vehicle {vehicle['id']} has bike but no valid route to any parking spots.")
            return False # No valid place to drop off

    # Task 2: Pick up a misplaced bike if vehicle has no bike
    else:
        best_target_bike = None
        min_travel_time = float('inf')
        eligible_misplaced_bike_ids = [bike_id for bike_id, status in all_bikes_state.items() if status == "misplaced"]

        for bike_id in eligible_misplaced_bike_ids:
            target_bike_node_id = next(b["node_id"] for b in bikes if b["id"] == bike_id)
            
            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, target_bike_node_id)
            if route_polyline and route_polyline[-1][2] > 0:
                travel_time = route_polyline[-1][2]
                if travel_time < min_travel_time:
                    min_travel_time = travel_time
                    best_target_bike = bike_id
                    best_route_polyline = route_polyline
        
        if best_target_bike:
            vehicle["current_task"] = "to_bike"
            vehicle["current_bike_id"] = best_target_bike
            vehicle["current_route_polyline"] = best_route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = min_travel_time
            all_bikes_state[best_target_bike] = "on_vehicle_en_route" # Mark bike as being picked up
            logger.debug(f"Vehicle {vehicle['id']} assigned to pick up bike {best_target_bike} (travel time: {min_travel_time:.2f}s).")
            return True
        else:
            logger.debug(f"Vehicle {vehicle['id']} has no bike and no available misplaced bikes with valid routes.")
            
            # Task 3: Reposition to a random parking spot if no misplaced bikes are available
            if not parking_spots:
                logger.debug(f"Vehicle {vehicle['id']} has no bike, no misplaced bikes, and no parking spots to reposition to.")
                return False # No parking spots to reposition to

            target_parking_spot = random.choice(parking_spots)
            target_node_id = target_parking_spot["node_id"]
            
            route_polyline = helper._get_route_polyline_from_node_ids(vehicle_node_id, target_node_id)
            if not route_polyline or route_polyline[-1][2] == 0:
                logger.debug(f"Vehicle {vehicle['id']} (repositioning) - No valid route to random target parking {target_node_id}.")
                return False # No valid route or zero travel time
            
            vehicle["current_task"] = "repositioning"
            vehicle["current_bike_id"] = None
            vehicle["current_route_polyline"] = route_polyline
            vehicle["current_route_start_time"] = current_sim_time
            vehicle["current_route_total_time"] = route_polyline[-1][2]
            logger.debug(f"Vehicle {vehicle['id']} assigned to reposition to parking {target_parking_spot['id']} (travel time: {route_polyline[-1][2]:.2f}s).")
            return True

# --- Simulation Loop ---
simulation_data = []
current_sim_time = 0 # seconds
last_bike_appearance_time = 0

while current_sim_time <= SIMULATION_DURATION_MINUTES * 60:
    # Dynamic bike appearance (only if current_sim_time is a multiple of BIKE_APPEARANCE_INTERVAL_SECONDS)
    if current_sim_time > 0 and (current_sim_time - last_bike_appearance_time >= BIKE_APPEARANCE_INTERVAL_SECONDS):
        logger.debug(f"Attempting to activate bikes at {current_sim_time}s.")
        inactive_bikes = [bike_id for bike_id, status in all_bikes_state.items() if status == "inactive"]
        logger.debug(f"all_bikes_state at {current_sim_time}s: {all_bikes_state}")
        logger.debug(f"Found {len(inactive_bikes)} inactive bikes: {inactive_bikes}")
        if inactive_bikes:
            bikes_to_activate = random.sample(inactive_bikes, min(BIKES_PER_INTERVAL, len(inactive_bikes)))
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
