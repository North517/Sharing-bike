from flask import Flask, render_template, jsonify
import os
import pandas as pd
import random
import sys
import multiprocessing
import shutil
import tempfile

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FLEETPY_MAIN_DIR) # Add FleetPy-main directory to sys.path

from run_examples import run_scenarios
import src.misc.config as config
from src.misc.globals import G_RANDOM_SEED, G_OP_DEPOT_F, G_RQ_FILE, G_SIM_REPLAY_FLAG
from src.utils.random_scenario_generator import generate_randomized_scenario_files

app = Flask(__name__)

FLEETPY_MAIN_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data_analysis')
def data_analysis():
    return render_template('data_analysis.html')

@app.route('/configuration')
def configuration():
    return render_template('configuration.html')

@app.route('/events')
def events():
    return render_template('events.html')

@app.route('/heatmap')
def heatmap():
    return render_template('heatmap.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/simulation_data.json')
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


current_simulation_process = None

def run_simulation_process(new_random_seed, study_path, scenario_path, constant_config_file_orig, scenario_file_orig):
    try:
        import tempfile
        import shutil
        import logging
        # Configure logging for the subprocess
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        LOG = logging.getLogger(__name__)
        LOG.setLevel(logging.DEBUG)

        # Create a temporary directory
        temp_dir = tempfile.mkdtemp()
        temp_constant_config_file = os.path.join(temp_dir, "constant_config_bike_rebalancing_temp.csv")

        # Load the original constant config
        constant_cfg = config.ConstantConfig(constant_config_file_orig)
        
        # Generate randomized scenario files in the temporary directory
        temp_station_file, temp_request_file = generate_randomized_scenario_files(FLEETPY_MAIN_DIR, temp_dir, new_random_seed)

        # Update the constant config with randomized files and new random seed
        constant_cfg[G_RANDOM_SEED] = new_random_seed
        constant_cfg[G_SIM_REPLAY_FLAG] = True
        constant_cfg[G_OP_DEPOT_F] = os.path.basename(temp_station_file)  # Only filename needed as it's in the scenario path
        constant_cfg[G_RQ_FILE] = os.path.basename(temp_request_file)  # Only filename needed

        # Write the modified constant config to the temporary file
        pd.DataFrame.from_dict(constant_cfg, orient='index', columns=['Parameter_Value']).to_csv(temp_constant_config_file, header=True, index_label='Input_Parameter_Name')

        # Adjust the scenario_file_orig path to the temporary directory if it's expected to be there
        # This might be needed if the scenario file also needs to be temporary or modified.
        # For now, assuming bike_rebalancing_scenario.csv doesn't need randomization and can be referenced directly
        # If the run_scenarios function expects this file to be in the same directory as constant_config_file,
        # then we might need to copy it to temp_dir or adjust the path. Let's assume it handles paths correctly for now.
        
        temp_scenario_file_path = os.path.join(temp_dir, os.path.basename(scenario_file_orig))
        shutil.copy(scenario_file_orig, temp_scenario_file_path)

        # Run the simulation with the modified constant config
        print(f"Starting simulation with random seed: {new_random_seed} using temp config: {temp_constant_config_file}")
        run_scenarios(temp_constant_config_file, temp_scenario_file_path, log_level="info", n_cpu_per_sim=1, n_parallel_sim=1)
        print(f"Simulation with random seed {new_random_seed} finished.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error in simulation process: {e}")
    finally:
        # Clean up the temporary directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


@app.route('/resimulate', methods=['POST'])
def resimulate():
    global current_simulation_process
    if current_simulation_process and current_simulation_process.is_alive():
        return jsonify({'error': 'A simulation is already running.'}), 409
    try:
        new_random_seed = random.randint(1, 100000)
        study_path = os.path.join(FLEETPY_MAIN_DIR, "studies", "bike_rebalancing_study")
        scenario_path = os.path.join(study_path, "scenarios")
        constant_config_file_orig = os.path.join(scenario_path, "constant_config_bike_rebalancing.csv")
        scenario_file_orig = os.path.join(scenario_path, "bike_rebalancing_scenario.csv")

        # Start the simulation in a new process
        current_simulation_process = multiprocessing.Process(target=run_simulation_process, args=(
            new_random_seed, study_path, scenario_path, constant_config_file_orig, scenario_file_orig))
        current_simulation_process.start()

        return jsonify({'message': f'Simulation re-started with new random seed: {new_random_seed}', 'process_id': current_simulation_process.pid}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error re-starting simulation: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)
