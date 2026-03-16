# -------------------------------------------------------------------------------------------------------------------- #
# standard distribution imports
# -----------------------------
from __future__ import annotations
import logging
import pandas as pd
import typing as tp

# src imports
# -----------
from src.misc.globals import *
from src.simulation.Legs import VehicleRouteLeg
from src.simulation.StationaryProcess import ChargingProcess

if tp.TYPE_CHECKING:
    from src.demand.TravelerModels import RequestBase
    from src.routing.NetworkBase import NetworkBase
    from src.fleetctrl.FleetControlBase import FleetControlBase

LOG = logging.getLogger(__name__)

# Simulation Vehicle class
# ------------------------
# > guarantee consistent movements in simulation and output
class SimulationVehicle:
    def __init__(self, operator_id : int, vehicle_id : int, vehicle_data_dir : str, vehicle_type : str, routing_engine : NetworkBase, rq_db : tp.Dict[tp.Any, RequestBase], op_output : str,
                 record_route_flag : bool, replay_flag : bool):
        """
        Initialization of vehicle in the simulation environment.
        :param operator_id: id of fleet operator the vehicle belongs to
        :param vehicle_id: id of the vehicle within the operator's fleet
        :param vehicle_data_dir: vehicle data directory
        :param vehicle_type: checks vehicle data base for existing model
        :param routing_engine: routing engine for queries
        :param rq_db: simulation request database (for conversion from plan requests)
        :param op_output: output for VRL records
        :param record_route_flag: generates path output if true
        :param replay_flag: generates extra output for replay visualization
        """
        self.op_id = operator_id
        self.vid = vehicle_id
        self.routing_engine = routing_engine
        self.rq_db = rq_db
        self.op_output = op_output
        self.record_route_flag = record_route_flag
        self.replay_flag = replay_flag
        #
        veh_data_f = os.path.join(vehicle_data_dir, f"{vehicle_type}.csv")
        veh_data = pd.read_csv(veh_data_f, header=None, index_col=0).squeeze("columns")
        self.veh_type = veh_data[G_VTYPE_NAME]
        self.max_pax = int(veh_data[G_VTYPE_MAX_PAX])
        self.max_parcels = int(veh_data.get(G_VTYPE_MAX_PARCELS, 0))
        self.daily_fix_cost = float(veh_data[G_VTYPE_FIX_COST])
        self.distance_cost = float(veh_data[G_VTYPE_DIST_COST])/1000.0
        self.battery_size = float(veh_data[G_VTYPE_BATTERY_SIZE])
        self.range = float(veh_data[G_VTYPE_RANGE])
        self.soc_per_m = 1/(self.range*1000)
        # current info
        self.status = VRL_STATES.IDLE
        self.pos = None
        self.soc = None
        self.pax: tp.List[RequestBase] = []  # rq_obj
        # assigned route = list of assigned vehicle legs
        self.assigned_route: tp.List[VehicleRouteLeg] = []
        # current leg (cl) info
        self.cl_start_time = None
        self.cl_start_pos = None
        self.cl_start_soc = None
        self.cl_toll_costs = 0
        self.cl_driven_distance = 0.0
        self.cl_driven_route = []  # list of passed node_indices
        self.cl_driven_route_times = []  # list of times at which nodes were passed; only filled for replay flag
        self.cl_remaining_route = []  # list of remaining nodes to next stop
        self.cl_remaining_time = None
        self.cl_locked = False
        # cumulative distance
        self.cumulative_distance = 0.0
        # TODO # check and think about consistent way for large time steps -> will vehicles wait until next update?
        self.start_next_leg_first = False   # flag, if True, a new assignment has been made, which has to be activated first in the next call of update_veh_state

    def __str__(self):
        return f"veh {self.vid} at pos {self.pos} with soc {self.soc} leg status {self.status} remaining time {self.cl_remaining_time} number remaining legs: {len(self.assigned_route)} ob : {[rq.get_rid_struct() for rq in self.pax]}"

    def reset_current_leg(self):
        # current info
        self.status = VRL_STATES.IDLE
        # add distance to cumulative distance
        self.cumulative_distance += self.cl_driven_distance

        # current leg (cl) info
        self.cl_start_time = None
        self.cl_start_pos = None
        self.cl_start_soc = None
        self.cl_toll_costs = 0
        self.cl_driven_distance = 0.0
        self.cl_driven_route = []  # list of passed node_indices
        self.cl_driven_route_times = []  # list of times at which nodes were passed; only filled for replay flag
        self.cl_remaining_route = []  # list of remaining nodes to next stop
        self.cl_remaining_time = None
        self.cl_locked = False

    def set_initial_state(self, fleetctrl:FleetControlBase, routing_engine:NetworkBase, state_dict:dict, start_time:int, veh_init_blocking:bool=True):
        """
        This method positions the vehicle at the beginning of a simulation. This method has to be called after
        the initialization of the operator FleetControl classes!

        :param fleetctrl: FleetControl of vehicle operator
        :param routing_engine: Routing Engine
        :param state_dict: see documentation/init_state.md for specification
        :param start_time: simulation start time
        :param veh_init_blocking: if this flag is set, the vehicles are blocked until final_time; otherwise,
                            only the position and soc are used at the start_time of the simulation
        :return:
        """
        self.status = VRL_STATES.IDLE
        self.pos = routing_engine.return_node_position(state_dict[G_V_INIT_NODE])
        self.soc = state_dict[G_V_INIT_SOC]
        if veh_init_blocking:
            final_time = state_dict[G_V_INIT_TIME]
            if final_time > start_time:
                init_blocked_duration = final_time-start_time
                self.status = VRL_STATES.BLOCKED_INIT
                fleetctrl.set_init_blocked(self, start_time, routing_engine, init_blocked_duration)
                self.assigned_route.append(VehicleRouteLeg(VRL_STATES.BLOCKED_INIT, (int(state_dict[G_V_INIT_NODE]), None, None), {},
                                                           duration=init_blocked_duration, locked=True))
                # self.start_next_leg(start_time)
                self.start_next_leg_first = True

    def return_final_state(self, sim_end_time:int)->tp.Dict[str, tp.Any]:
        """
        This method returns the required information to save the currently assigned route. For simplicity, the
        start node is used for vehicles that end up in the middle of a link and the soc at the end of the simulation
        run is used. Only the time is checked.
        :return: {}: key > value
        """
        final_state_dict = {G_V_OP_ID:self.op_id, G_V_VID:self.vid, G_V_INIT_SOC:self.soc}
        if self.assigned_route:
            final_state_dict[G_V_INIT_NODE] = self.assigned_route[-1].destination_pos[0]
            last_time = sim_end_time
            last_pos = self.pos
            for leg in self.assigned_route:
                leg_end_pos = leg.destination_pos
                if leg_end_pos != last_pos:
                    _, tt, _ = self.routing_engine.return_travel_costs_1to1(last_pos, leg_end_pos)
                    last_pos = leg_end_pos
                    last_time += tt
                elif leg.duration:
                    last_time += leg.duration
            end_time = last_time
        else:
            final_state_dict[G_V_INIT_NODE] = self.pos[0]
            end_time = sim_end_time
        # beware of not blocking a vehicle for a whole day!
        final_state_dict[G_V_INIT_TIME] = end_time % (24*3600)
        return final_state_dict

    def _start_next_leg_stationary_object(self, simulation_time:int)->tp.Tuple[tp.List[RequestBase], tp.List[RequestBase]]:
        """ Starts the next leg using the route leg with a stationary process """

        # TODO: Generalize the current method and incoporate directly into the start_next_leg method
        ca = self.assigned_route[0]
        remaining_time_to_start = ca.stationary_process.remaining_time_to_start(simulation_time)
        if remaining_time_to_start is not None and remaining_time_to_start > 0:
            # insert waiting leg
            waiting_vrl = VehicleRouteLeg(VRL_STATES.WAITING, self.pos, {}, duration=remaining_time_to_start)
            self.assigned_route = [waiting_vrl] + self.assigned_route
            LOG.debug("veh start next leg waiting at time {} remaining {} : {}".format(simulation_time,
                                                                                       remaining_time_to_start,
                                                                                       self))
            return self.start_next_leg(simulation_time)
        else:
            self.cl_remaining_route = []
            LOG.debug("start stationary process at {}: duration before : {}".format(simulation_time, self.cl_remaining_time))
            ca.stationary_process.start_task(simulation_time)
            self.cl_remaining_time = ca.stationary_process.remaining_duration_to_finish(simulation_time)
            LOG.debug("duration after: {}".format(self.cl_remaining_time))
            return [], []
    
    def start_next_leg(self, simulation_time:int)->tp.Tuple[tp.List[RequestBase], tp.List[RequestBase]]:
        """
        This function resets the current task attributes of a vehicle. Furthermore, it returns a list of currently
        boarding requests.
        :param simulation_time
        :return: list of currently boarding requests, list of starting to alight requests
        """
        if self.assigned_route:
            LOG.debug(f"start_next_leg {self.vid} : {self.assigned_route[0]}")
        else:
            LOG.debug(f"start_next_leg {self.vid} : no")
        if self.assigned_route and simulation_time >= self.assigned_route[0].earliest_start_time:
            LOG.debug(f"Vehicle {self.vid} starts new VRL {self.assigned_route[0].__dict__} at time {simulation_time}")
            self.cl_start_time = simulation_time
            self.cl_start_pos = self.pos
            self.cl_start_soc = self.soc
            self.cl_driven_distance = 0.0
            ca = self.assigned_route[0]
            if self.replay_flag:
                self.cl_driven_route = [self.pos[0]]
                self.cl_driven_route_times = [simulation_time]
            else:
                self.cl_driven_route = []
        if self.replay_flag:
            self.cl_driven_route.append(self.pos[0])
            self.cl_driven_route_times.append(simulation_time)
            self.status = ca.status
            if self.pos != ca.destination_pos:
                if ca.route and self.pos[0] == ca.route[0]:
                    self.cl_remaining_route = ca.route
                else:
                    self.cl_remaining_route = self._compute_new_route(ca.destination_pos)
                try:
                    self.cl_remaining_route.remove(self.pos[0])
                except ValueError:
                    # TODO # check out after ISTTT
                    LOG.warning(f"First node in position {self.pos} not found in currently assigned route {ca.route}!")

                self.cl_remaining_time = None
                list_boarding_pax = []
                list_start_alighting_pax = []
            elif ca.stationary_process is not None:
                list_boarding_pax = []
                list_start_alighting_pax = []
                self._start_next_leg_stationary_object(simulation_time)
            else:
                # VehicleChargeLeg: check whether duration should be changed (other SOC value or late arrival)
                if ca.status == VRL_STATES.CHARGING:
                    ca.set_duration_at_start(simulation_time, self)
                self.cl_remaining_route = []
                if ca.duration is not None:
                    self.cl_remaining_time = ca.duration
                    if ca.earliest_end_time > simulation_time + self.cl_remaining_time:
                        self.cl_remaining_time = ca.earliest_end_time - simulation_time
                    if ca.status in G_LOCK_DURATION_STATUS:
                        ca.locked = True
                else:
                    if not ca.locked:
                        # this will usually only happen for waiting tasks, which can be stopped at any time
                        self.cl_remaining_time = None
                    else:
                        # raise AssertionError(f"Current locked task of vehicle {self.vid}"
                        #                      f"(operator {self.op_id}) has no stop criterion!")
                        LOG.info(f"Current locked task of vehicle {self.vid} (operator {self.op_id}) has no stop"
                                 f" criterion!")
                list_boarding_pax = [rq.get_rid_struct() for rq in ca.rq_dict.get(1, [])]
                list_start_alighting_pax = [rq.get_rid_struct() for rq in ca.rq_dict.get(-1, [])]
                for rq_obj in ca.rq_dict.get(1, []):
                    self.pax.append(rq_obj)
                LOG.debug(f"boarding the vehicle: bd: {list_boarding_pax} db: {list_start_alighting_pax} pax {self.pax}")
            LOG.debug("veh start next leg boarding at time {} remaining {}: {}".format(simulation_time, self.cl_remaining_time, self))
            return list_boarding_pax, list_start_alighting_pax
        elif self.assigned_route and simulation_time < self.assigned_route[0].earliest_start_time:
            # insert waiting leg
            waiting_vrl = VehicleRouteLeg(VRL_STATES.WAITING, self.pos, {}, duration=self.assigned_route[0].earliest_start_time - simulation_time)
            self.assigned_route = [waiting_vrl] + self.assigned_route
            LOG.debug("veh start next leg waiting at time {} remaining {} : {}".format(simulation_time, self.cl_remaining_time, self))
            return self.start_next_leg(simulation_time)
        else:
            LOG.debug("veh start next leg at time {} remaining {}: {}".format(simulation_time, self.cl_remaining_time, self))
            return [], []

    def end_current_leg(self, simulation_time:int)->tp.Tuple[tp.List[int], VehicleRouteLeg]:
        LOG.debug(f"end_current_leg for veh {self.vid} at time {simulation_time}. Assigned route length: {len(self.assigned_route)}")
        """
        This method stops the current leg, creates the record dictionary, and shifts the list of legs in the
        assigned route. It returns a list of alighting passengers and the record dictionary.
        :param simulation_time
        :return: (list_alight, passed_VRL)
            [rid1, rid2] given by int value
            passed_VRL: VRL object
        """
        if self.assigned_route and not self.start_next_leg_first:
            ca = self.assigned_route[0]
            LOG.debug(f"Vehicle {self.vid} ends the VRL {ca} at time {simulation_time}")
            if ca.stationary_process is not None:
                ca.stationary_process.end_task(simulation_time)
            # record
            record_dict = {}
            record_dict[G_V_OP_ID] = self.op_id
            record_dict[G_V_VID] = self.vid
            record_dict[G_V_TYPE] = self.veh_type
            record_dict[G_VR_STATUS] = self.status.display_name
            record_dict[G_VR_LOCKED] = ca.locked
            record_dict[G_VR_LEG_START_TIME] = self.cl_start_time
            record_dict[G_VR_LEG_END_TIME] = simulation_time
            if self.cl_start_pos is None:
                LOG.error(f"current cl starting point not set before! {self.vid} {self.status.display_name} {self.cl_start_time}")
                raise EnvironmentError
            record_dict[G_VR_LEG_START_POS] = self.routing_engine.return_position_str(self.cl_start_pos)
            record_dict[G_VR_LEG_END_POS] = self.routing_engine.return_position_str(self.pos)
            record_dict[G_VR_LEG_DISTANCE] = self.cl_driven_distance
            record_dict[G_VR_LEG_START_SOC] = self.cl_start_soc
            record_dict[G_VR_LEG_END_SOC] = self.soc
            record_dict[G_VR_CHARGING_POWER] = ca.power
            if ca.stationary_process is not None and type(ca.stationary_process) == ChargingProcess:
                station_id = ca.stationary_process.station.id
                socket_id = ca.stationary_process.socket_id
                record_dict[G_VR_CHARGING_UNIT] = f"{station_id}-{socket_id}"
            else:
                record_dict[G_VR_CHARGING_UNIT] = ""
            record_dict[G_VR_TOLL] = self.cl_toll_costs
            record_dict[G_VR_OB_RID] = ";".join([str(rq.get_rid_struct()) for rq in self.pax])
            record_dict[G_VR_NR_PAX] = sum([rq.nr_pax for rq in self.pax])
            # remove and record alighting passengers
            list_boarding_pax = [rq.get_rid_struct() for rq in ca.rq_dict.get(1, [])]
            list_alighting_pax = [rq.get_rid_struct() for rq in ca.rq_dict.get(-1, [])]
            for rq_obj in ca.rq_dict.get(-1, []):
                try:
                    self.pax.remove(rq_obj)
                except:
                    LOG.warning(f"Could not remove passenger {rq_obj.get_rid_struct()} from vehicle {self.vid}"
                                f" at time {simulation_time}")
            record_dict[G_VR_BOARDING_RID] = ";".join([str(rid) for rid in list_boarding_pax])
            record_dict[G_VR_ALIGHTING_RID] = ";".join([str(rid) for rid in list_alighting_pax])
            if self.record_route_flag:
                record_dict[G_VR_NODE_LIST] = ";".join([str(x) for x in self.cl_driven_route])
            # Only create route_replay_str if replay_flag is True and route data is available
            current_sim_time = simulation_time # Assign to a local variable
            route_replay_str = ""
            if self.replay_flag and self.cl_driven_route and len(self.cl_driven_route) == len(self.cl_driven_route_times):
                route_replay_str = ";".join([f"{self.cl_driven_route[i]}:{self.cl_driven_route_times[i]}"\
                                             for i in range(len(self.cl_driven_route))])
            else:
                if self.replay_flag:
                    LOG.warning(f"Vehicle {self.vid} has inconsistent route data for replay at time {current_sim_time}. "
                                f"cl_driven_route length: {len(self.cl_driven_route)}, "
                                f"cl_driven_route_times length: {len(self.cl_driven_route_times)}")
            record_dict[G_VR_REPLAY_ROUTE] = route_replay_str
            # default status and shift to next leg
            self.reset_current_leg()
            self.assigned_route = self.assigned_route[1:]
            self.op_output.append(record_dict)
            return list_alighting_pax, ca
        elif self.start_next_leg_first:
            # this can happen when user_request makes assignment and batch optimization in same time step makes
            # different assignment
            LOG.debug(f"vid {self.vid}: another assignment in same step? end_leg not called")
            return ([], {})
        else:
            LOG.warning(f"Trying to stop a leg of vehicle {self.vid} at time {simulation_time} "
                        f"even though no route is assigned!")
            return ([], {})
        
    def assign_vehicle_plan(self, list_route_legs : tp.List[VehicleRouteLeg], sim_time:int, force_ignore_lock:bool = False):
        """This method enables the fleet control modules to assign a plan to the simulation vehicles. It ends the
        previously assigned leg and starts the new one if necessary.
        :param list_route_legs: list of legs to assign to vehicle
        :type list_route_legs: list of VehicleRouteLeg
        :param sim_time: current simulation time
        :type sim_time: int
        :param force_ignore_lock: this parameter allows overwriting locked VehicleRouteLegs, except a boarding process allready started
        :type force_ignore_lock: bool
        """
        # transform rq from PlanRequest to SimulationRequest (based on RequestBase)
        # LOG.info(f"Vehicle {self.vid} before new assignment: {[str(x) for x in self.assigned_route]} at time {sim_time}")
        for vrl in list_route_legs:
            boarding_list = [self.rq_db[prq.get_rid()] for prq in vrl.rq_dict.get(1,[])]
            alighting_list = [self.rq_db[prq.get_rid()] for prq in vrl.rq_dict.get(-1,[])]
            vrl.rq_dict = {1:boarding_list, -1:alighting_list}
        LOG.debug(f"Vehicle {self.vid} received new VRLs {[str(x) for x in list_route_legs]} at time {sim_time}")
        LOG.debug(f"  -> current assignment: {[str(x) for x in self.assigned_route]}")
        LOG.debug(f" -> force: {force_ignore_lock}")
        start_flag = True
        if self.assigned_route:
            if not list_route_legs or list_route_legs[0] != self.assigned_route[0]:
                if list_route_legs and self.status == VRL_STATES.WAITING and list_route_legs[0].earliest_start_time > sim_time: # dont write multiple waiting legs
                    LOG.debug(f"update waiting time for {self.vid} at {sim_time} from {self.cl_remaining_time} to {list_route_legs[0].earliest_start_time - sim_time}")
                    self.cl_remaining_time = list_route_legs[0].earliest_start_time - sim_time
                    list_route_legs = [self.assigned_route[0]] + list_route_legs
                    list_route_legs[0].duration = list_route_legs[1].earliest_start_time - self.cl_start_time
                    start_flag = False
                else:
                    if not self.assigned_route[0].locked:
                        self.end_current_leg(sim_time)
                    else:
                        if force_ignore_lock and not self.assigned_route[0].status == VRL_STATES.BOARDING:
                            self.end_current_leg(sim_time)
                        else:
                            LOG.error("vid : {}".format(self.vid))
                            LOG.error("currently assigned: {}".format([str(x) for x in self.assigned_route]))
                            LOG.error("new: {}".format([str(x) for x in list_route_legs]))
                            LOG.error("current additional infos: {}".format(self.assigned_route[0].additional_str_infos()))
                            LOG.error("new additional infos: {}".format(list_route_legs[0].additional_str_infos()))
                            raise AssertionError("assign_vehicle_plan(): Trying to assign new VRLs instead of a locked VRL.")
            else:
                start_flag = False

        self.assigned_route = list_route_legs
        if list_route_legs:
            if start_flag:
                self.start_next_leg_first = True
                # print("THIS IS NOT ALLOWED TO HAPPEN HERE IN CASE OF IMIDIATE BOARDINGS/DEBOARDINGS") # TODO #
                # exit()
                # self.start_next_leg(sim_time)
        # LOG.info(f"Vehicle {self.vid} after new assignment: {[str(x) for x in self.assigned_route]} at time {sim_time}")

    def update_veh_state(self, simulation_time:int, routing_engine:NetworkBase, current_time:float=None)->tp.Tuple[tp.List[int], tp.List[int], tp.List[RequestBase], tp.List[RequestBase]]:
        """
        This method is called every simulation step. It updates the vehicle position and state.
        :param simulation_time: current simulation time
        :param routing_engine: routing engine
        :param current_time: current time within the simulation step. if given, vehicle position is updated to current_time
        :return: (list_alighting_pax_rid, list_boarding_pax_rid, list_start_alighting_rQ_obj, list_start_boarding_rQ_obj)
        """
        # check if new assignment should be started
        if self.start_next_leg_first:
            list_boarding_pax, list_start_alighting_pax = self.start_next_leg(simulation_time)
            self.start_next_leg_first = False
            return [], [], list_start_alighting_pax, list_boarding_pax
        #
        # vehicle is blocked and cannot perform any task
        if self.status == VRL_STATES.BLOCKED_INIT:
            if self.assigned_route[0].earliest_start_time <= simulation_time:
                self.end_current_leg(simulation_time)
            return [], [], [], []
        #
        # current leg in progress
        list_alighting_pax_rid = []
        list_boarding_pax_rid = []
        list_start_alighting_rq_obj = []
        list_start_boarding_rq_obj = []
        #
        if self.cl_remaining_time is None: # driving tasks
            # how much time remaining in this simulation step
            remaining_step_time = simulation_time + 1 - current_time if current_time else 1.0
            #
            arrival_in_time_step = self._move(current_time, remaining_step_time, simulation_time)
            if arrival_in_time_step >= 0: # end of leg is reached
                if self.assigned_route: # new leg will be started in current time step
                    list_alighting_pax_rid, passed_VRL = self.end_current_leg(arrival_in_time_step)
                    list_start_alighting_rq_obj = []
                    # start new leg
                    list_boarding_pax_rid, list_start_boarding_rq_obj = self.start_next_leg(arrival_in_time_step)
                else: # no new leg -> vehicle idle
                    list_alighting_pax_rid, passed_VRL = self.end_current_leg(arrival_in_time_step)
                    list_start_alighting_rq_obj = []
            else: # no arrival in this time step -> still driving
                pass
        else: # stationary tasks
            if self.cl_remaining_time <= 1: # end of leg is reached
                if self.assigned_route: # new leg will be started in current time step
                    list_alighting_pax_rid, passed_VRL = self.end_current_leg(simulation_time+1)
                    list_start_alighting_rq_obj = passed_VRL.rq_dict.get(-1, [])
                    # start new leg
                    list_boarding_pax_rid, list_start_boarding_rq_obj = self.start_next_leg(simulation_time+1)
                else: # no new leg -> vehicle idle
                    list_alighting_pax_rid, passed_VRL = self.end_current_leg(simulation_time+1)
                    list_start_alighting_rq_obj = passed_VRL.rq_dict.get(-1, [])
            else: # no arrival in this time step -> still stationary
                self.cl_remaining_time -= 1
        return list_alighting_pax_rid, list_boarding_pax_rid, list_start_alighting_rq_obj, list_start_boarding_rq_obj

    def update_route(self):
        if self.assigned_route:
            ca = self.assigned_route[0]
            if self.pos != ca.destination_pos:
                self.cl_remaining_route = self._compute_new_route(ca.destination_pos)
                try:
                    self.cl_remaining_route.remove(self.pos[0])
                except ValueError:
                    # TODO # check out after ISTTT
                    LOG.warning(f"First node in position {self.pos} not found in currently assigned route {ca.route}!")
                # LOG.info(f"veh {self.vid} update route {self.pos} -> {ca.destination_pos} : {self.cl_remaining_route}")

    def _move(self, c_time:float, remaining_step_time:float, update_start_time:float)->float:
        """ this function is used internally to move the vehicle when called in update_veh_state
            -> can be overwritten in case no movement is performed within the simulation framework but externally
        :param c_time: start_time of the moving process
        :param remaining_step_time: remaining time of the current update step
        :param update_start_time: time when update step started
        :return: arrival in time step (-1 if still moving at end of update step, time of arrival at end of route otherwise"""        
        LOG.debug(f"Vehicle {self.vid} replay_flag: {self.replay_flag} before move_along_route")
        (new_pos, driven_distance, arrival_in_time_step, passed_nodes, passed_node_times) = \
            self.routing_engine.move_along_route(self.cl_remaining_route, self.pos, remaining_step_time,\
                                                    sim_vid_id=(self.op_id, self.vid),\
                                                    new_sim_time=current_time,\
                                                    record_node_times=self.replay_flag)
        self.pos = new_pos
        # Update cl_remaining_route based on the new position
        if self.cl_remaining_route and new_pos[0] in self.cl_remaining_route:
            # Find the index of the new position's node in the current remaining route
            try:
                index_of_new_pos = self.cl_remaining_route.index(new_pos[0])
                # Truncate the route, starting from the node AFTER the current position
                # because new_pos[0] is the current node, not a node to be passed.
                self.cl_remaining_route = self.cl_remaining_route[index_of_new_pos + 1:]
            except ValueError:
                # This should theoretically not happen if new_pos[0] was in cl_remaining_route
                LOG.error(f"Error: Node {new_pos[0]} not found in cl_remaining_route after check.")
        else:
            # If new_pos[0] is not in the remaining route, it means the route is completed
            # or there's an inconsistency.
            self.cl_remaining_route = []
        # Removed the redundant assignment of last_node for clarity and moved its usage. Changed it to c_node
        c_node = self.pos[0]
        self.cl_driven_distance += driven_distance
        self.soc -= driven_distance * self.soc_per_m
        if self.replay_flag and passed_nodes:
            self.cl_driven_route.extend(passed_nodes)
            self.cl_driven_route_times.extend(passed_node_times)
        for node in passed_nodes:
            tmp_toll_route = [c_node, node]
            # TODO #
            _, toll_costs, _ = \
                self.routing_engine.get_zones_external_route_costs(update_start_time,
                                                                    tmp_toll_route,
                                                                    park_origin=False, park_destination=False)
            self.cl_toll_costs += toll_costs
            c_node = node

        return arrival_in_time_step

    def _compute_new_route(self, target_pos:tuple)->tp.List[int]:
        """ this function is used internally when the route has to be updated
        this is usefull in case it has to be overwritten to trigger additional processes
        :param target_pos: destination position tuple
        :return: list of node ids (route from pos to target_pos)"""
        return self.routing_engine.return_best_route_1to1(self.pos, target_pos)


class AimsunVehicle(SimulationVehicle):
    """
    This class inherits from the SimulationVehicle and has additional attributes and methods required for the
    interaction with Aimsun.
    """
    def __init__(self, operator_id, vehicle_id, vehicle_data_dir, vehicle_type, routing_engine, rq_db, op_output, record_route_flag, replay_flag):
        super().__init__(operator_id, vehicle_id, vehicle_data_dir, vehicle_type, routing_engine, rq_db, op_output, record_route_flag, replay_flag)
        self._route_update_needed = False # set true if new route available or vehicle doesnt move on planned route

    def update_vehicle_position(self, veh_pos, simulation_time):
        """ this method is used to update the vehicle position in the network
        ! veh_pos can also be None to register if vehicles dont move !
        :param veh_pos: network position tuple (start_node, end_node, rel_pos) or (current_node, None, None)
        :param simulation_time: current simulation time """
        #LOG.debug(f"update pos {self} -> {veh_pos}")
        if self.status in G_DRIVING_STATUS:
            if veh_pos is None:
                LOG.debug("non moving vehicle registered? {}".format(self))
                self._route_update_needed = True
            else:
                self.pos = veh_pos
                #print(f'self.os {self.pos}')
                if self.pos[0] in self.cl_remaining_route:
                    i = self.cl_remaining_route.index(self.pos[0])
                    dr = self.cl_remaining_route[:i+1]
                    self.cl_driven_route.extend(dr)
                    self.cl_driven_route_times.extend(passed_node_times[len(self.cl_driven_route_times):len(self.cl_driven_route_times)+len(dr)])
                    self.cl_remaining_route = self.cl_remaining_route[i+1:]
                if self.pos[1] is not None:
                    if len(self.cl_remaining_route) > 0 and self.cl_remaining_route[0] != self.pos[1]:
                        LOG.warning("vehicle no longer on route!")
                        LOG.warning(f"{self}")
                        LOG.warning(f"time {simulation_time} pos {self.pos} remaining route {self.cl_remaining_route} driven route {self.cl_driven_route}")
                        self.update_route()
                        self._route_update_needed = True
                    elif len(self.cl_remaining_route) == 0:
                        LOG.warning("no route planned anymore? {} {}".format(veh_pos, self))
                else:
                    #LOG.warning("vehicle stands on node, but is driving...")
                    if self.cl_remaining_route: # vehicle still has a route
                        if self.pos[0] != self.cl_remaining_route[0]:
                            LOG.warning("vehicle has route but is on wrong node. compute new route")
                            self.update_route()
                            self._route_update_needed = True
                    elif self.assigned_route and self.assigned_route[0].destination_pos[0] != self.pos[0]: # vehicle has a task but no route
                        LOG.warning("vehicle has task but no route. compute new route")
                        self.update_route()
                        self._route_update_needed = True
        elif veh_pos is not None and not self.start_next_leg_first:
            raise EnvironmentError(f"moving without having a driving task? {self}")

    def _compute_new_route(self, target_pos):
        """ a new route has to be computed -> set also flag that this route will be sent to vehicle controller """
        self._route_update_needed = True
        LOG.debug(" -> compute new route for {}".format(self))
        return super()._compute_new_route(target_pos)

    def get_new_route(self):
        """ this function is used to return the current pos of the vehicle and the route that is needed to be driven in the aimsun simulation
        if something is return (i.e. a new driven vrl needs to be started) is indicated by the flag self.start_new_route_flag
        :return: None, if no route has to be started; node_index_list otherwise
        """
        #LOG.debug(f"get_pos_and_route: {self.vid} | {self.start_new_route_flag} | {self.assigned_route} | {self.pos} | {self.cl_remaining_route}")
        #LOG.debug('Is this ever entered?')
        if self._route_update_needed:
            #LOG.debug(f"new route for vehicle {self}")
            self._route_update_needed = False
            if not self.assigned_route:
                if self.pos[1] is not None:
                    LOG.debug(f" -> {self.vid} -> {[self.pos[0], self.pos[1]]}")
                    return [self.pos[0], self.pos[1]]
                else:
                    LOG.warning("new route to start after unassignment but on edge!")
                    LOG.debug(f" -> {self.vid} -> {[self.pos[0]]}")
                    return [self.pos[0]]
            else:
                route = self.cl_remaining_route
                route = [self.pos[0]] + route
                LOG.debug(f" -> {self.vid} -> {route}")
                return route
        else:
            #LOG.debug('_route_update_needed is False')
            return None

    def assign_vehicle_plan(self, list_route_legs, sim_time, force_ignore_lock = False):
        """This method enables the fleet control modules to assign a plan to the simulation vehicles. It ends the
        previously assigned leg and starts the new one if necessary.
        :param list_route_legs: list of legs to assign to vehicle
        :type list_route_legs: list of VehicleRouteLeg
        :param sim_time: current simulation time
        :type sim_time: int
        :param force_ignore_lock: this parameter allows overwriting locked VehicleRouteLegs, except a boarding process allready started
        :type force_ignore_lock: bool
        """
        # transform rq from PlanRequest to SimulationRequest (based on RequestBase)
        # LOG.info(f"Vehicle {self.vid} before new assignment: {[str(x) for x in self.assigned_route]} at time {sim_time}")
        for vrl in list_route_legs:
            boarding_list = [self.rq_db[prq.get_rid()] for prq in vrl.rq_dict.get(1,[])]
            alighting_list = [self.rq_db[prq.get_rid()] for prq in vrl.rq_dict.get(-1,[])]
            vrl.rq_dict = {1:boarding_list, -1:alighting_list}
        #LOG.debug(f"Vehicle {self.vid} received new VRLs {[str(x) for x in list_route_legs]} at time {sim_time}")
        #LOG.debug(f"  -> current assignment: {self.assigned_route}")
        start_flag = True
        if self.assigned_route:
            if not list_route_legs or list_route_legs[0] != self.assigned_route[0]:
                if not self.assigned_route[0].locked:
                    self.end_current_leg(sim_time)
                else:
                    if force_ignore_lock and not self.assigned_route[0].status == VRL_STATES.BOARDING:
                        self.end_current_leg(sim_time)
                    else:
                        LOG.error("vid : {}".format(self.vid))
                        LOG.error("currently assigned: {}".format([str(x) for x in self.assigned_route]))
                        LOG.error("new: {}".format([str(x) for x in list_route_legs]))
                        LOG.error("current additional infos: {}".format(self.assigned_route[0].additional_str_infos()))
                        LOG.error("new additional infos: {}".format(list_route_legs[0].additional_str_infos()))
                        raise AssertionError("assign_vehicle_plan(): Trying to assign new VRLs instead of a locked VRL.")
            else:
                start_flag = False

        self.assigned_route = list_route_legs
        if list_route_legs:
            if start_flag:
                self.start_next_leg_first = True
                if self.status in G_DRIVING_STATUS:
                    if not self.assigned_route[0].status in G_DRIVING_STATUS:
                        LOG.warning("while currently driving a new route without start driving vrl assigned {} {}".format(self, list_route_legs))
                        driving_vrl = VehicleRouteLeg(self.status, self.assigned_route[0].destination_pos, {})
                        self.assigned_route = [driving_vrl] + self.assigned_route[:]
        else: # check if vehicle needs to be stopped in aimsun control
            if self.status in G_DRIVING_STATUS:
                self._route_update_needed = True

    def _get_travel_time_to_assigned_next_pos(self, current_time):
        if self.assigned_route:
            first_leg = self.assigned_route[0]
            if first_leg.status == VRL_STATES.DRIVING and self.pos != first_leg.destination_pos:
                return self.routing_engine.return_travel_time_1to1(self.pos, first_leg.destination_pos, current_time)
        return 0

    def _get_current_pax_rid_list(self):
        return [pax.get_rid_struct() for pax in self.pax]

    def _get_current_pax_obj_list(self):
        return self.pax

    def _get_pos(self):
        return self.pos

    def _set_pos(self, val):
        self.pos = val

    def _get_soc(self):
        return self.soc

    def _set_soc(self, val):
        self.soc = val

    def _get_vid(self):
        return self.vid
    
    def _get_op_id(self):
        return self.op_id
    
    def _get_current_status(self):
        return self.status

    def get_status_info(self):
        if self.status == VRL_STATES.DRIVING and self.cl_remaining_route:
            return self.status.display_name, self.cl_remaining_route[0]
        else:
            return self.status.display_name, None

    def compute_soc_consumption(self, distance):
        """
        This method computes the SOC consumption for a given distance.
        :param distance: distance in meters
        :return: SOC consumption
        """
        return distance * self.soc_per_m

    def check_if_reached_destination(self, simulation_time, full_simulation_time, allow_dest_node_mismatch=False):
        """
        This function is used to check if the vehicle reached its current destination.
        :param simulation_time:
        :param full_simulation_time: current simulation time (since beginning of simulation)
        :param allow_dest_node_mismatch: if this is true, the destination node might be different from the actual position if only one link was missed
        :return:
        """
        if self.assigned_route:
            target_pos = self.assigned_route[0].destination_pos
            if self.pos != target_pos:
                LOG.debug(f"veh {self.vid} not at destination: pos {self.pos} target {target_pos} for leg {self.assigned_route[0].__dict__}")
                if allow_dest_node_mismatch and self.pos[1] is not None and target_pos[1] is None and self.pos[0] == target_pos[0]:
                    LOG.debug(" -> allow_dest_node_mismatch: vehicle is on link, destination is node. but same start node. OK!")
                    self.pos = target_pos
                    return
                # if vehicle is in different position than target_pos -> compute new route
                r = self._compute_new_route(target_pos)
                if len(r) <= 2:
                    LOG.debug("only one edge missed: if this is a turn, everything is fine! route: {}".format(r))
                    self.pos = target_pos
                    self.cl_driven_route.append(target_pos[0])
                    self.cl_driven_route_times.append( full_simulation_time )
                    self._route_update_needed = False
                elif self.routing_engine.return_route_infos(r, 0, 0)[0] < 0.1:
                    LOG.debug("more edges but very short edges -> assume reached destination!")
                    self.pos = target_pos
                    for x in r[1:]:
                        self.cl_driven_route.append(x)
                        self.cl_driven_route_times.append( full_simulation_time )
                    self._route_update_needed = False
                else:
                    LOG.warning(f"vehicle {self.vid} did not reach destination {target_pos} from {self.pos} at time {simulation_time}! -> new route {r}")
                    self.cl_remaining_route = r
        elif self.pos[1] is not None:
            # this happens when no assigned route is present and vehicle moves for some reason
            # -> vehicle needs to move to node
            LOG.warning(f"vehicle {self.vid} has no assigned route but is on link {self.pos}. move to node!")
            self.cl_remaining_route = self._compute_new_route( (self.pos[0], None, None) )
