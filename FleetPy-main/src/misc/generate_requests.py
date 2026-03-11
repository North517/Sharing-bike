import pandas as pd
import random

# Configuration
NUM_REQUESTS = 50
SIM_DURATION = 7200  # seconds (2 hours)
DEPOT_NODES = [2966, 2980]
NODES_FILE = "E:\\Sharing bike\\FleetPy-main\\FleetPy-main\\data\\networks\\example_network\\base\\nodes.csv"
OUTPUT_FILE = "E:\\Sharing bike\\FleetPy-main\\FleetPy-main\\data\\demand\\example_demand\\matched\\example_network\\bike_rebalancing_requests.csv"

def generate_requests():
    # Read all possible node_index from nodes.csv
    nodes_df = pd.read_csv(NODES_FILE)
    all_node_indices = nodes_df['node_index'].tolist()

    requests = []
    for i in range(NUM_REQUESTS):
        rq_time = random.randint(0, SIM_DURATION)
        start_node = random.choice(all_node_indices)
        end_node = random.choice(DEPOT_NODES) # Randomly assign to one of the parking spots
        request_id = i

        requests.append({
            'rq_time': rq_time,
            'start': start_node,
            'end': end_node,
            'request_id': request_id
        })

    requests_df = pd.DataFrame(requests)
    requests_df = requests_df.sort_values(by='rq_time').reset_index(drop=True)
    requests_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Generated {NUM_REQUESTS} requests to {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_requests()
