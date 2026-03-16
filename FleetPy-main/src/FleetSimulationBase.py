# -------------------------------------------------------------------------------------------------------------------- #
# standard distribution imports
# -----------------------------
import os
import importlib
import logging
import random
import time
import datetime
from abc import abstractmethod
from tqdm import tqdm
import typing as tp
from pathlib import Path
from multiprocessing import Manager
import json

logging.VERBOSE = 5
logging.addLevelName(logging.VERBOSE, "VERBOSE")
logging.Logger.verbose = lambda inst, msg, *args, **kwargs: inst.log(logging.VERBOSE, msg, *args, **kwargs)
logging.LoggerAdapter.verbose = lambda inst, msg, *args, **kwargs: inst.log(logging.VERBOSE, msg, *args, **kwargs)
logging.verbose = lambda msg, *args, **kwargs: logging.log(logging.VERBOSE, msg, *args, **kwargs)

# additional module imports (> requirements)
# ------------------------------------------
import pandas as pd
import numpy as np

# src imports
# -----------
from src.misc.init_modules import load_fleet_control_module, load_routing_engine, load_broker_module, build_operator_attribute_dicts
from src.misc.globals import *
from src.demand.demand import Demand
from src.simulation.Vehicles import SimulationVehicle
if tp.TYPE_CHECKING:
    from src.fleetctrl.FleetControlBase import FleetControlBase
    from src.routing.NetworkBase import NetworkBase
    from src.broker.BrokerBase import BrokerBase

# -------------------------------------------------------------------------------------------------------------------- #
# global variables
# ----------------
DEFAULT_LOG_LEVEL = logging.DEBUG

log_file_path = os.path.join(os.path.dirname(__file__), "..", "output", "00_simulation.log")
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.root.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s-%(process)d-%(name)s-%(levelname)s-%(message)s')
os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logging.root.addHandler(file_handler)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(formatter)
logging.root.addHandler(stream_handler)

LOG = logging.getLogger(__name__)
LOG.propagate = False
LOG.setLevel(logging.DEBUG)
BUFFER_SIZE = 1000
PROGRESS_LOOP = "demand"
PROGRESS_LOOP_VEHICLE_STATUS = [VRL_STATES.IDLE,VRL_STATES.CHARGING,VRL_STATES.REPOSITION]

INPUT_PARAMETERS_FleetSimulationBase = {
    "doc" : "base simulation class",
    "inherit" : None,
    "input_parameters_mandatory": [
        G_SCENARIO_NAME, G_SIM_START_TIME, G_SIM_END_TIME, G_NR_OPERATORS, G_RANDOM_SEED, G_NETWORK_NAME,
        G_DEMAND_NAME, G_RQ_FILE, G_AR_MAX_DEC_T
    ],
    "input_parameters_optional": [
        G_SIM_TIME_STEP, G_NR_CH_OPERATORS, G_SIM_REALTIME_PLOT_FLAG, "log_level", G_SIM_ROUTE_OUT_FLAG, G_SIM_REPLAY_FLAG, G_INIT_STATE_SCENARIO,
        G_ZONE_SYSTEM_NAME, G_INFRA_NAME
    ],
    "mandatory_modules": [
        G_SIM_ENV, G_NETWORK_TYPE, G_RQ_TYP1, G_OP_MODULE
    ],
    "optional_modules": []
}


# -------------------------------------------------------------------------------------------------------------------- #
def create_or_empty_dir(dirname):
    if os.path.isdir(dirname):
        if(dirname == '/' or dirname == "\\"):
            return
        else:
            for root, dirs, files in os.walk(dirname, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
    else:
        os.makedirs(dirname)


# -------------------------------------------------------------------------------------------------------------------- #
class FleetSimulationBase:
    def __init__(self, scenario_parameters: dict):
        self.t_init_start = time.perf_counter()
        self.scenario_name = scenario_parameters[G_SCENARIO_NAME]
        print("-"*80 + f"\nSimulation of scenario {self.scenario_name}")

        if scenario_parameters.get("show_progress_bar", True) is False:
            global PROGRESS_LOOP
            PROGRESS_LOOP = "off"
        
        self.n_op = scenario_parameters[G_NR_OPERATORS]
        self.n_ch_op = scenario_parameters.get(G_NR_CH_OPERATORS, 0)

        self.list_op_dicts: tp.Dict[str,str] = build_operator_attribute_dicts(scenario_parameters, self.n_op, prefix="op_")
        self.list_ch_op_dicts: tp.Dict[str,str] = build_operator_attribute_dicts(scenario_parameters, self.n_ch_op, prefix="ch_op_")
        
        self.dir_names = self.get_directory_dict(scenario_parameters, self.list_op_dicts)
        create_or_empty_dir(self.dir_names[G_DIR_WEB_VIS_OUTPUT])
        self.skip_output = True if scenario_parameters.get(G_SKIP_OUTPUT, 0) > 0 else False
        if not self.skip_output:
            create_or_empty_dir(self.dir_names[G_DIR_OUTPUT])

        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        log_level_str = scenario_parameters.get(G_LOG_LEVEL, "info").lower()
        log_level = logging.INFO
        if log_level_str == "verbose":
            log_level = logging.VERBOSE
        elif log_level_str == "debug":
            log_level = logging.DEBUG
        elif log_level_str == "warning":
            log_level = logging.WARNING
        logging.root.setLevel(log_level)


        formatter = logging.Formatter('%(asctime)s-%(process)d-%(name)s-%(levelname)s-%(message)s')
        log_file_path = os.path.join(self.dir_names[G_DIR_OUTPUT], "00_simulation.log")
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logging.root.addHandler(file_handler)
        stream_handler = logging.StreamHandler()
        
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        logging.root.addHandler(stream_handler)

        LOG.info(f"Initializing {self.scenario_name}")
        self.scenario_parameters: dict = scenario_parameters
        final_state_f = os.path.join(self.dir_names[G_DIR_OUTPUT], "final_state.csv")
        if self.scenario_parameters.get("keep_old", False) and os.path.isfile(final_state_f):
            print(f"Simulation {self.scenario_name} already exists! Skipping.")
            self._started = True
            return
        else:
            self._started = False

        self.start_time = self.scenario_parameters[G_SIM_START_TIME]
        self.end_time = self.scenario_parameters[G_SIM_END_TIME]
        self.time_step = self.scenario_parameters.get(G_SIM_TIME_STEP, 1)
        self.check_sim_env_spec_inputs(self.scenario_parameters)
        self._manager: tp.Optional[Manager] = None
        self._shared_dict: dict = {}
        self._plot_class_instance = None
        self.realtime_plot_flag = self.scenario_parameters.get(G_SIM_REALTIME_PLOT_FLAG, 0)
        self.simulation_data_history = []

        random.seed(self.scenario_parameters[G_RANDOM_SEED])
        np.random.seed(self.scenario_parameters[G_RANDOM_SEED])

        if not self.skip_output:
            create_or_empty_dir(self.dir_names[G_DIR_OUTPUT])
        self.save_scenario_inputs()
        if self.skip_output:
            LOG.disabled = True

        self.user_stat_f = os.path.join(self.dir_names[G_DIR_OUTPUT], f"1_user-stats.csv")
        self.network_stat_f = os.path.join(self.dir_names[G_DIR_OUTPUT], f"3_network-stats.csv")
        self.pt_stat_f = os.path.join(self.dir_names[G_DIR_OUTPUT], "4_pt_stats.csv")

        self.zones = None
        if self.dir_names.get(G_DIR_ZONES, None) is not None:
            from src.infra.NetworkZoning import NetworkZoneSystem
            self.zones = NetworkZoneSystem(self.dir_names[G_DIR_ZONES], self.scenario_parameters, self.dir_names)

        LOG.info("Loading network...")
        network_type = self.scenario_parameters[G_NETWORK_TYPE]
        nw_dyn_file = self.scenario_parameters.get(G_NW_DYNAMIC_F, None)
        self.routing_engine = load_routing_engine(network_type, self.dir_names[G_DIR_NETWORK], network_dynamics_file_name=nw_dyn_file)

        LOG.info("Loading demand...")
        self.demand = None
        self._load_demand_module()
        self.charging_operator_dict = {}
        self._load_charging_modules()

        self.sim_vehicles: tp.Dict[tp.Tuple[int, int], SimulationVehicle] = {}
        self.operators: tp.List[FleetControlBase] = []
        self.op_output = {}
        self._load_fleetctr_vehicles()

        self.init_blocking = True
        self.add_init(self.scenario_parameters)
        self.load_initial_state()
        self.broker = None
        self._load_broker_module()

    def _load_demand_module(self):
        demand_class = self.scenario_parameters.get("demand_class", "Demand")
        demand_mod = self.scenario_parameters.get("demand_module", "demand")
        mod = importlib.import_module(f"src.demand.{demand_mod}")
        cls = getattr(mod, demand_class)
        self.demand = cls(self.scenario_parameters, self.user_stat_f, self.routing_engine, self.zones)
        self.demand.load_demand_file(
            self.start_time, self.end_time, self.dir_names[G_DIR_DEMAND],
            self.scenario_parameters[G_RQ_FILE], self.scenario_parameters[G_RANDOM_SEED],
            self.scenario_parameters.get(G_RQ_TYP1), self.scenario_parameters.get(G_RQ_TYP2, {}),
            self.scenario_parameters.get(G_RQ_TYP3, {}), simulation_time_step=self.time_step
        )

    def _load_charging_modules(self):
        self.charging_operator_dict = {"op": {}, "pub": {}}
        if self.dir_names.get(G_DIR_INFRA):
            from src.infra.ChargingInfrastructure import OperatorChargingAndDepotInfrastructure
            for op_id, op_dict in enumerate(self.list_op_dicts):
                depot_f = op_dict.get(G_OP_DEPOT_F)
                if depot_f:
                    path = os.path.join(self.dir_names[G_DIR_INFRA], depot_f)
                    self.charging_operator_dict["op"][op_id] = OperatorChargingAndDepotInfrastructure(
                        op_id, path, op_dict, self.scenario_parameters, self.dir_names, self.routing_engine
                    )
            if self.list_ch_op_dicts:
                from src.infra.ChargingInfrastructure import PublicChargingInfrastructureOperator
                for ch_id, ch_dict in enumerate(self.list_ch_op_dicts):
                    cs_f = ch_dict.get(G_CH_OP_F)
                    path = os.path.join(self.dir_names[G_DIR_INFRA], cs_f)
                    self.charging_operator_dict["pub"][ch_id] = PublicChargingInfrastructureOperator(
                        ch_id, path, ch_dict, self.scenario_parameters, self.dir_names, self.routing_engine
                    )

    def _load_fleetctr_vehicles(self):
        LOG.info("Loading fleet...")
        route_out = self.scenario_parameters.get(G_SIM_ROUTE_OUT_FLAG, True)
        replay = self.scenario_parameters.get(G_SIM_REPLAY_FLAG, False)
        vt_list = []
        for op_id in range(self.n_op):
            op_attr = self.list_op_dicts[op_id]
            op_dirs = self.dir_names.copy()
            op_dirs.update(self.dir_names.get(f"op_{op_id}", {}))
            self.op_output[op_id] = []
            vehs = []
            fleet_comp = op_attr.get("op_fleet_composition")
            if fleet_comp:
                for comp in fleet_comp.split(";"):
                    vtype, num = comp.split(":")
                    num = int(num)
                    vfile = os.path.join(self.dir_names[G_DIR_VEH], f"{vtype}_instances.csv")
                    df = pd.read_csv(vfile)
                    for i in range(num):
                        vid = df.loc[i, "veh_id"]
                        v = SimulationVehicle(op_id, vid, self.dir_names[G_DIR_VEH], vtype, self.routing_engine, self.demand.rq_db, self.op_output[op_id], route_out, replay)
                        vehs.append(v)
                        self.sim_vehicles[(op_id, vid)] = v
                OpCls = load_fleet_control_module(op_attr[G_OP_MODULE])
                self.operators.append(OpCls(op_id, op_attr, vehs, self.routing_engine, self.zones, self.scenario_parameters, op_dirs, self.charging_operator_dict["op"].get(op_id), list(self.charging_operator_dict["pub"].values())))
            else:
                OpCls = load_fleet_control_module(op_attr[G_OP_MODULE])
                op = OpCls(op_id, op_attr, [], self.routing_engine, self.zones, self.scenario_parameters, op_dirs, self.charging_operator_dict["op"].get(op_id), list(self.charging_operator_dict["pub"].values()))
                inits = op.return_vehicles_to_initialize()
                for vid, vtype in inits.items():
                    v = SimulationVehicle(op_id, vid, self.dir_names[G_DIR_VEH], vtype, self.routing_engine, self.demand.rq_db, self.op_output[op_id], route_out, replay)
                    vehs.append(v)
                    self.sim_vehicles[(op_id, vid)] = v
                op.continue_init(vehs, self.start_time, self.end_time)
                self.operators.append(op)
        vt_list = [[v.op_id, v.vid, v.veh_type] for v in self.sim_vehicles.values()]
        pd.DataFrame(vt_list, columns=[G_V_OP_ID, G_V_VID, G_V_TYPE]).to_csv(os.path.join(self.dir_names[G_DIR_OUTPUT], "2_vehicle_types.csv"), index=False)
        self.sorted_sim_vehicle_keys = sorted(self.sim_vehicles.keys())
        self.vehicle_update_order = {k:1 for k in self.sim_vehicles.keys()}

    def _load_broker_module(self):
        btype = self.scenario_parameters.get(G_BROKER_TYPE, "BrokerBasic")
        cls = load_broker_module(btype)
        self.broker = cls(self.n_op, self.operators)

    @staticmethod
    def get_directory_dict(scenario_parameters, list_operator_dicts):
        return get_directory_dict(scenario_parameters, list_operator_dicts)

    def save_scenario_inputs(self):
        if self.skip_output:
            return
        p = os.path.join(self.dir_names[G_DIR_OUTPUT], G_SC_INP_F)
        with open(p, "w") as f:
            json.dump({
                "scenario_parameters": self.scenario_parameters,
                "list_operator_attributes": self.list_op_dicts,
                "directories": self.dir_names
            }, f, indent=4)

    def evaluate(self):
        from src.evaluation.standard import standard_evaluation
        standard_evaluation(self.dir_names[G_DIR_OUTPUT])
        self.add_evaluate()

    def load_initial_state(self):
        init_path = None
        if self.scenario_parameters.get(G_INIT_STATE_SCENARIO):
            init_path = os.path.join(self.dir_names[G_DIR_MAIN], "studies", self.scenario_parameters[G_STUDY_NAME], "results", str(self.scenario_parameters[G_INIT_STATE_SCENARIO]), "final_state.csv")
        unassigned = set((v.op_id, v.vid) for v in self.sim_vehicles.values() if v.pos is None)
        if init_path and os.path.exists(init_path):
            df = pd.read_csv(init_path).set_index([G_V_OP_ID, G_V_VID])
            for key in unassigned:
                if key in df.index:
                    v = self.sim_vehicles[key]
                    v.set_initial_state(self.operators[key[0]], self.routing_engine, df.loc[key], self.start_time, self.init_blocking)
        for key in unassigned:
            v = self.sim_vehicles[key]
            if v.pos is None:
                nodes = self.routing_engine.get_must_stop_nodes() or list(range(self.routing_engine.get_number_network_nodes()))
                node = np.random.choice(nodes)
                v.set_initial_state(self.operators[key[0]], self.routing_engine, {G_V_INIT_NODE: node, G_V_INIT_TIME: self.start_time, G_V_INIT_SOC: 0.75}, self.start_time, self.init_blocking)

    def save_final_state(self):
        if self.skip_output:
            return
        data = [v.return_final_state(self.end_time) for v in self.sim_vehicles.values()]
        pd.DataFrame(data).to_csv(os.path.join(self.dir_names[G_DIR_OUTPUT], "final_state.csv"), index=False)

    def record_remaining_assignments(self):
        t = self.end_time
        rem = 1
        while rem:
            self.update_sim_state_fleets(t-self.time_step, t)
            rem = sum(len(v.assigned_route) for v in self.sim_vehicles.values())
            t += self.time_step
            if t > self.end_time + 7200:
                break

    def record_stats(self, force=True):
        if self.skip_output:
            return
        self.demand.save_user_stats(force)
        for op_id, buf in self.op_output.items():
            if (force and buf) or len(buf) > BUFFER_SIZE:
                p = os.path.join(self.dir_names[G_DIR_OUTPUT], f"2-{op_id}_op-stats.csv")
                mode = "a" if os.path.exists(p) else "w"
                header = not os.path.exists(p)
                pd.DataFrame(buf).to_csv(p, index=False, mode=mode, header=header)
                buf.clear()

    def update_sim_state_fleets(self, last, next):
        for key, v in sorted(self.sim_vehicles.items(), key=lambda x: self.vehicle_update_order[x[0]]):
            op, vid = key
            alighted_rids, boarded_rids, start_alighting_rq_objs, start_boarding_rq_objs = v.update_veh_state(last, next)
            # Process newly boarded passengers
            for rid in boarded_rids:
                self.demand.record_boarding(rid, vid, op, next, pu_pos=v.pos)
                self.broker.acknowledge_user_boarding(op, rid, vid, next)
            # Process passengers starting to alight
            for rq_obj in start_alighting_rq_objs:
                rid = rq_obj.get_rid()
                self.demand.record_alighting_start(rid, vid, op, next, do_pos=v.pos)
            # Process newly alighted passengers
            for rid in alighted_rids:
                self.demand.user_ends_alighting(rid, vid, op, next)
                self.broker.acknowledge_user_alighting(op, rid, vid, next)

    def run(self):
        if self._started:
            return
        self._started = True
        total = len(self.demand.future_requests)
        with tqdm(total=100) as pbar:
            for t_sim in range(self.start_time, self.end_time, self.time_step):
                self.step(t_sim)
                veh_ids, veh_st, veh_data, mb_rids, mb_coords, ps_ids, ps_coords = self._get_current_simulation_state(t_sim)
                self._collect_web_visualization_data(t_sim, veh_ids, veh_st, veh_data, mb_rids, mb_coords, ps_ids, ps_coords)
                rem = sum(len(x) for x in self.demand.future_requests.values())
                pbar.n = min(100, int(100 * (1 - rem / max(total,1))))
                pbar.set_postfix({"sim_time": t_sim, "idle": sum(1 for v in self.sim_vehicles.values() if v.status == VRL_STATES.IDLE)})
        self.record_stats()
        self.save_final_state()
        self.record_remaining_assignments()
        self.evaluate()
        self._write_web_visualization_data()

    def _write_web_visualization_data(self):
        if self.skip_output:
            return
        json_output_path = os.path.join(self.dir_names[G_DIR_WEB_VIS_OUTPUT], "simulation_data.json")
        LOG.info(f"Attempting to create directory for: {json_output_path}")
        os.makedirs(os.path.dirname(json_output_path), exist_ok=True)
        LOG.info(f"Parent directory exists after creation: {os.path.isdir(os.path.dirname(json_output_path))}")
        with open(json_output_path, 'w') as f:
            json.dump(self.simulation_data_history, f, indent=4)

    def _get_current_simulation_state(self, sim_time):
        veh_ids = []
        veh_st = []
        veh_data = []
        for key in self.sorted_sim_vehicle_keys:
            v = self.sim_vehicles[key]
            veh_ids.append(key)
            veh_st.append(v.status)
            veh_data.append({
                "id": key, "status": v.status, "current_pos": v.pos,
                "cl_start_time": v.cl_start_time, "cl_driven_route": v.cl_driven_route,
                "cl_driven_route_times": v.cl_driven_route_times, "replay_flag": v.replay_flag,
                "cl_end_time": getattr(v, "cl_end_time", None),
                "cl_end_pos": getattr(v, "cl_end_pos", None),
                "soc": getattr(v, "soc", 1.0), "pax": getattr(v, "pax", 0)
            })
        mb_rids, mb_pos = [], []
        for rid, rq in self.demand.get_undecided_travelers(sim_time):
            mb_rids.append(rid)
            mb_pos.append(rq.o_pos)
        mb_coords = self.routing_engine.return_positions_lon_lat(mb_pos)
        ps_ids, ps_pos = [], []
        if self.charging_operator_dict.get("op"):
            op = next(iter(self.charging_operator_dict["op"].values()))
            for d_id, d in op.depot_by_id.items():
                ps_ids.append(d_id)
                ps_pos.append(d.pos)
        ps_coords = self.routing_engine.return_positions_lon_lat(ps_pos)
        return veh_ids, veh_st, veh_data, mb_rids, mb_coords, ps_ids, ps_coords

    def _collect_web_visualization_data(self, sim_time, veh_ids, veh_status, veh_data_for_web, misplaced_bike_rids, misplaced_bike_coords, parking_spot_ids, parking_spot_coords):
        from src.ReplayFromResult import State
        current = {"time": sim_time, "vehicles": [], "misplaced_bikes": [], "parking_spots": []}
        for d in veh_data_for_web:
            vid = d["id"]
            st = d["status"]
            pos = d["current_pos"]
            route = d["cl_driven_route"]
            times = d["cl_driven_route_times"]
            t_start = d["cl_start_time"]

            end_pos = d.get("cl_end_pos") or pos
            end_t = d.get("cl_end_time") or sim_time + 60

            if not route or not times:
                lonlat = self.routing_engine.return_positions_lon_lat([pos])[0]
                current["vehicles"].append({"id": f"{vid[0]}-{vid[1]}", "status": st.value, "lon": lonlat[0], "lat": lonlat[1]})
                continue

            s = State(
                vid_str=f"{vid[0]}-{vid[1]}", time=t_start, pos=pos,
                end_time=end_t, end_pos=end_pos, soc=d.get("soc",1), pax=d.get("pax",0),
                moving=True, status=st.name, parcels=0, passengers=0,
                route=route, times=times, routing_engine=self.routing_engine
            )
            res = s.return_state(sim_time)
            vehicle_entry = {"id": f"{vid[0]}-{vid[1]}", "status": st.value}

            if res and "nw_pos" in res:
                lonlat = self.routing_engine.return_positions_lon_lat([res["nw_pos"]])[0]
                vehicle_entry["lon"] = lonlat[0]
                vehicle_entry["lat"] = lonlat[1]
            else:
                lonlat = self.routing_engine.return_positions_lon_lat([pos])[0]
                vehicle_entry["lon"] = lonlat[0]
                vehicle_entry["lat"] = lonlat[1]

            if route and times: # Check if route and times are available from d
                # Convert list of node IDs to list of (node_id, None, None) position tuples
                route_positions = [(node_id, None, None) for node_id in route]
                route_lonlats = self.routing_engine.return_positions_lon_lat(route_positions)
                vehicle_entry["route_lonlats"] = route_lonlats
                vehicle_entry["route_times"] = times

            current["vehicles"].append(vehicle_entry)

        for rid, (lon, lat) in zip(misplaced_bike_rids, misplaced_bike_coords):
            current["misplaced_bikes"].append({"id": int(rid), "lon": lon, "lat": lat})
        for pid, (lon, lat) in zip(parking_spot_ids, parking_spot_coords):
            current["parking_spots"].append({"id": int(pid), "lon": lon, "lat": lat})

        self.simulation_data_history.append(current)

    def count_fleet_status(self):
        c = {s:0 for s in VRL_STATES}
        for v in self.sim_vehicles.values():
            c[v.status] += 1
        return c

    @abstractmethod
    def step(self, sim_time):
        pass

    @abstractmethod
    def check_sim_env_spec_inputs(self, scenario_parameters):
        return scenario_parameters

    def add_init(self, scenario_parameters):
        for op, attr in zip(self.operators, self.list_op_dicts):
            op.add_init(attr, scenario_parameters)

    @abstractmethod
    def add_evaluate(self):
        pass