from flask import Flask, render_template, jsonify
import os

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

@app.route('/simulation_data.json')
def get_simulation_data():
    file_path = os.path.join(FLEETPY_MAIN_DIR, 'simulation_data.json')
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'application/json'}
    return jsonify({'error': 'simulation_data.json not found'}), 404


if __name__ == '__main__':
    app.run(debug=True, port=8000)
