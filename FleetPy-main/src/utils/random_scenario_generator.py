import os
import pandas as pd
import random
import numpy as np

def generate_randomized_scenario_files(fleetpy_main_dir, temp_output_dir, random_seed, num_stations=2, num_requests=50):
    """
    Generates randomized scenario files (campus_parking_spots.csv and bike_rebalancing_requests.csv)
    based on available network nodes.

    Args:
        fleetpy_main_dir (str): The base path to the FleetPy-main directory (for reading original files like nodes.csv).
        temp_output_dir (str): The temporary directory where generated files will be saved.
        random_seed (int): The random seed for reproducibility.
        num_stations (int): Number of stations to generate.
        num_requests (int): Number of bike requests to generate.

    Returns:
        tuple: Paths to the generated temporary station and request CSV files.
    """
    random.seed(random_seed)
    np.random.seed(random_seed)

    # Define paths
    network_nodes_path = os.path.join(fleetpy_main_dir, "data", "networks", "example_network", "base", "nodes.csv")

    # Load all available node indices
    nodes_df = pd.read_csv(network_nodes_path)
    all_node_indices = nodes_df["node_index"].tolist()

    if len(all_node_indices) < num_stations:
        raise ValueError(f"Not enough unique nodes ({len(all_node_indices)}) for {num_stations} stations.")
    # It's possible to have more requests than nodes, as requests are pairs of nodes.
    # if len(all_node_indices) < num_requests:
    #     raise ValueError(f"Not enough unique nodes ({len(all_node_indices)}) for {num_requests} bike requests.")

    # --- Randomize Stations (Green Dots) ---
    temp_station_file_path = os.path.join(temp_output_dir, "campus_parking_spots.csv")
    
    # Select random unique node indices for stations
    station_nodes = random.sample(all_node_indices, num_stations)
    
    station_data = []
    for i, node_idx in enumerate(station_nodes):
        max_nr_parking = random.randint(10, 50)  # Random parking capacity
        # For simplicity, using a single charging unit type, could be randomized further
        charging_units = f"{7.5}:{random.randint(0,5)};{15.0}:{random.randint(0,5)}"
        station_data.append({
            "charging_station_id": i,
            "max_nr_parking": max_nr_parking,
            "charging_units": charging_units,
            "node_index": node_idx
        })
    temp_stations_df = pd.DataFrame(station_data)
    temp_stations_df.to_csv(temp_station_file_path, index=False)
    print(f"Generated temporary station file: {temp_station_file_path}")

    # --- Randomize Bike Rebalancing Requests (Red Dots) ---
    temp_request_file_path = os.path.join(temp_output_dir, "bike_rebalancing_requests.csv")

    request_data = []
    for i in range(num_requests):
        start_node = random.choice(all_node_indices)
        end_node = random.choice(all_node_indices)
        while start_node == end_node: # Ensure start and end nodes are different
            end_node = random.choice(all_node_indices)
        
        rq_time = random.randint(0, 7000) # Random request time within simulation timeframe
        request_data.append({
            "rq_time": rq_time,
            "start": start_node,
            "end": end_node,
            "request_id": i
        })
    temp_requests_df = pd.DataFrame(request_data)
    temp_requests_df.to_csv(temp_request_file_path, index=False)
    print(f"Generated temporary request file: {temp_request_file_path}")

    return temp_station_file_path, temp_request_file_path
