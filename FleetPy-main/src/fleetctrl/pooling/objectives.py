from __future__ import annotations
import logging
import numpy as np

import logging
from typing import TYPE_CHECKING, Dict, Any, Callable
if TYPE_CHECKING:
    from src.fleetctrl.planning.VehiclePlan import VehiclePlan
    from src.fleetctrl.planning.PlanRequest import PlanRequest
    from src.simulation.Vehicles import SimulationVehicle
    from src.routing.NetworkBase import NetworkBase

LOG = logging.getLogger(__name__)

from src.misc.globals import *

LARGE_INT = 1000000
MAX_DISTANCE = 100 * 1000  # 100 km -> to define an assignment reward per request
MAX_DELAY = 2 * 60 * 60  # 2 hours -> to define an assignment reward per request
MAX_BASE_DISTANCE_COST = 100/1000  # 1 dollar per km

# -------------------------------------------------------------------------------------------------------------------- #
# main function
# -------------
def return_pooling_objective_function(vr_control_func_dict:dict)->Callable[[int,SimulationVehicle,VehiclePlan,Dict[Any,PlanRequest],NetworkBase],float]:
    """This function generates the control objective functions for vehicle-request assignment in pooling operation.
    The control objective functions contain an assignment reward of LARGE_INT and are to be
    ---------------
    -> minimized <-
    ---------------

    :param vr_control_func_dict: dictionary which has to contain "func_key" as switch between possible functions;
            additional parameters of a function can have additional keys.
    :type vr_control_func_dict: dict
    :return: objective function
    :rtype: function
    """
    func_key = vr_control_func_dict["func_key"]

    # ---------------------------------------------------------------------------------------------------------------- #
    # control objective function definitions
    # --------------------------------------
    if func_key == "total_distance":
        assignment_reward_per_rq = MAX_DISTANCE
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function evaluates the driven distance according to a vehicle plan.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            sum_dist = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_dist += routing_engine.return_travel_costs_1to1(last_pos, pos)[2]
                    last_pos = pos
            return sum_dist - assignment_reward

    elif func_key == "total_system_time":
        ignore_repo_stop_wt = vr_control_func_dict.get("irswt", False)
        assignment_reward_per_rq = MAX_DELAY * 10
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        if not ignore_repo_stop_wt:
            def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
                """This function evaluates the total spent time of a vehicle according to a vehicle plan.

                :param simulation_time: current simulation time
                :param veh_obj: simulation vehicle object
                :param veh_plan: vehicle plan in question
                :param rq_dict: rq -> Plan request dictionary
                :param routing_engine: for routing queries
                :return: objective function value
                """
                assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
                # end time (for request assignment purposes) defined by arrival at last stop
                if veh_plan.list_plan_stops:
                    end_time = veh_plan.list_plan_stops[-1].get_planned_arrival_and_departure_time()[0]
                else:
                    end_time = simulation_time
                # utility is negative value of end_time - simulation_time
                return end_time - simulation_time - assignment_reward
        else:
            def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
                """This function evaluates the total spent time of a vehicle according to a vehicle plan.
                If the last stop is an empty plan stop (i.e. repositioning or reservation) it only evaluates travel time, not waiting time
                (in case of reservation, there can be a huge waiting time which does not reflect the efficiancy of the plan)

                :param simulation_time: current simulation time
                :param veh_obj: simulation vehicle object
                :param veh_plan: vehicle plan in question
                :param rq_dict: rq -> Plan request dictionary
                :param routing_engine: for routing queries
                :return: objective function value
                """
                assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
                # end time (for request assignment purposes) defined by arrival at last stop
                if veh_plan.list_plan_stops:
                    if veh_plan.list_plan_stops[-1].is_locked_end():
                        if len(veh_plan.list_plan_stops) > 1:
                            prev_end_time = veh_plan.list_plan_stops[-2].get_planned_arrival_and_departure_time()[0]
                            end_time = prev_end_time + routing_engine.return_travel_costs_1to1(veh_plan.list_plan_stops[-2].get_pos(), veh_plan.list_plan_stops[-1].get_pos())[1]
                        else:
                            end_time = simulation_time + routing_engine.return_travel_costs_1to1(veh_obj.pos, veh_plan.list_plan_stops[-1].get_pos())[1]   
                    else:
                        end_time = veh_plan.list_plan_stops[-1].get_planned_arrival_and_departure_time()[0]
                else:
                    end_time = simulation_time
                # utility is negative value of end_time - simulation_time
                return end_time - simulation_time - assignment_reward

    elif func_key == "user_times":
        assignment_reward_per_rq = MAX_DELAY
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        
        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function evaluates the total spent time of a vehicle according to a vehicle plan.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            # value of time term (treat waiting and in-vehicle time the same)
            sum_user_times = 0
            for rid, boarding_info_list in veh_plan.pax_info.items():
                rq_time = rq_dict[rid].rq_time
                drop_off_time = boarding_info_list[1]
                sum_user_times += (drop_off_time - rq_time)
            # utility is negative value of end_time - simulation_time
            return sum_user_times  - assignment_reward
        
    elif func_key == "total_travel_times":
        assignment_reward_per_rq = MAX_DELAY * 10
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        
        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function evaluates the total travel time of the vehicle (no waiting/boarding, ...).

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            sum_tt = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_tt += routing_engine.return_travel_costs_1to1(last_pos, pos)[1]
                    last_pos = pos
            return sum_tt - assignment_reward

    elif func_key == "system_and_user_time":
        user_weight = vr_control_func_dict["uw"]
        assignment_reward_per_rq = MAX_DELAY * 10
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        
        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function calculates the total system time (time the plan takes to be completed) and the total user times
            (time from request till drop off). user times are weighted by the factor given from "uw".

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            # value of time term (treat waiting and in-vehicle time the same)
            sum_user_times = 0
            for rid, boarding_info_list in veh_plan.pax_info.items():
                rq_time = rq_dict[rid].rq_time
                drop_off_time = boarding_info_list[1]
                sum_user_times += (drop_off_time - rq_time)

            if veh_plan.list_plan_stops:
                end_time = veh_plan.list_plan_stops[-1].get_planned_arrival_and_departure_time()[0]
            else:
                end_time = simulation_time
            system_time = end_time - simulation_time
            #print("vid {}-> vids {} | simulation time {} : ctrf: sys time {} | user time {} | both {} | all {}".format(veh_obj.vid, veh_plan.get_dedicated_rid_list(), simulation_time, system_time, sum_user_times, system_time + user_weight*sum_user_times, system_time + user_weight*sum_user_times - assignment_reward))
            return system_time + user_weight*sum_user_times - assignment_reward

    elif func_key == "distance_and_user_times":
        traveler_vot = vr_control_func_dict["vot"]
        assignment_reward_per_rq = MAX_DISTANCE * MAX_BASE_DISTANCE_COST + MAX_DELAY * traveler_vot
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")

        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function combines the total driving costs and the value of customer time.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            # distance term
            sum_dist = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_dist += routing_engine.return_travel_costs_1to1(last_pos, pos)[2]
                    last_pos = pos
            # value of time term (treat waiting and in-vehicle time the same)
            sum_user_times = 0
            for rid, boarding_info_list in veh_plan.pax_info.items():
                rq_time = rq_dict[rid].rq_time
                drop_off_time = boarding_info_list[1]
                sum_user_times += (drop_off_time - rq_time)
            # vehicle costs are taken from simulation vehicle (cent per meter)
            # value of travel time is scenario input (cent per second)
            return sum_dist * veh_obj.distance_cost + sum_user_times * traveler_vot - assignment_reward

    elif func_key == "distance_and_user_times_man":
        traveler_vot = vr_control_func_dict["vot"]
        distance_cost = vr_control_func_dict["dc"]
        assignment_reward_per_rq = vr_control_func_dict.get("arw", None)
        if assignment_reward_per_rq is None:
            assignment_reward_per_rq = MAX_DISTANCE * distance_cost + MAX_DELAY * traveler_vot
            assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        ignore_reservation_stop = vr_control_func_dict.get("irs", True) # ignore travel distance to reservation stop (last in plan; usually far in the future)
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        LOG.info(f" -> ignore_reservation_stop: {ignore_reservation_stop}")
        reassignment_penalty = vr_control_func_dict.get("p_reassign", None)  # penalty for reassigning a request

        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function combines the total driving costs and the value of customer time.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = len(veh_plan.pax_info) * assignment_reward_per_rq
            # distance term
            sum_dist = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                if ps.is_locked_end() and ignore_reservation_stop:
                    break
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_dist += routing_engine.return_travel_costs_1to1(last_pos, pos)[2]
                    last_pos = pos
            # value of time term (treat waiting and in-vehicle time the same)
            sum_user_times = 0
            for rid, boarding_info_list in veh_plan.pax_info.items():
                rq_time = rq_dict[rid].rq_time
                drop_off_time = boarding_info_list[1]
                sum_user_times += (drop_off_time - rq_time)
                
            # reassignment penalty
            if reassignment_penalty is not None:
                for rid in veh_plan.pax_info.keys():
                    offer = rq_dict[rid].get_current_offer()
                    if offer is not None and offer.get("vid") is not None and offer["vid"] != veh_obj.vid:
                        LOG.debug(f" -> reassigning request {rid} from {offer['vid']} to {veh_obj.vid} with penalty {reassignment_penalty}")
                        assignment_reward -= reassignment_penalty
            # vehicle costs are taken from simulation vehicle (cent per meter)
            # value of travel time is scenario input (cent per second)
            # LOG.debug(f" -> obj eval: sum_dist {sum_dist} * distance_cost {distance_cost} + sum_user_times {sum_user_times} * traveler_vot {traveler_vot} - assignment_reward {assignment_reward}")
            return sum_dist * distance_cost + sum_user_times * traveler_vot - assignment_reward
        
    elif func_key == "distance_and_user_times_man_with_reservation":
        traveler_vot = vr_control_func_dict["vot"]
        distance_cost = vr_control_func_dict["dc"]
        reservation_rq_weight = vr_control_func_dict.get("rrw", 10) # reward factor for assigning not assigned reservation requests
        assignment_reward_per_rq = MAX_DISTANCE * distance_cost + MAX_DELAY * traveler_vot
        assignment_reward_per_rq = 10 ** np.ceil(np.log10(assignment_reward_per_rq))
        ignore_reservation_stop = vr_control_func_dict.get("irs", True) # ignore travel distance to reservation stop (last in plan; usually far in the future)
        ignore_user_cost_horizon = vr_control_func_dict.get("iuch", None) # ignore user cost horizon for reservation requests
        LOG.info(f" -> assignment_reward_per_rq for objective function: {assignment_reward_per_rq}")
        LOG.info(f" -> ignore_reservation_stop: {ignore_reservation_stop}")
        LOG.info(f" -> ignore_user_cost_horizon: {ignore_user_cost_horizon}")

        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function combines the total driving costs and the value of customer time.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            assignment_reward = 0
            for rid in veh_plan.pax_info.keys():
                if rq_dict[rid].get_reservation_flag():
                    assignment_reward += reservation_rq_weight * assignment_reward_per_rq
                else:
                    assignment_reward += assignment_reward_per_rq
                    
            # distance term
            sum_dist = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                if ps.is_locked_end() and ignore_reservation_stop:
                    break
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_dist += routing_engine.return_travel_costs_1to1(last_pos, pos)[2]
                    last_pos = pos
            # value of time term (treat waiting and in-vehicle time the same)
            sum_user_times = 0
            for rid, boarding_info_list in veh_plan.pax_info.items():
                #rq_time = rq_dict[rid].rq_time
                ept = rq_dict[rid].get_o_stop_info()[1]
                if ignore_user_cost_horizon is not None and ept - simulation_time > ignore_user_cost_horizon:
                    continue
                drop_off_time = boarding_info_list[1]
                sum_user_times += (drop_off_time - ept)
            # vehicle costs are taken from simulation vehicle (cent per meter)
            # value of travel time is scenario input (cent per second)
            # LOG.debug(f" -> obj eval: sum_dist {sum_dist} * distance_cost {distance_cost} + sum_user_times {sum_user_times} * traveler_vot {traveler_vot} - assignment_reward {assignment_reward}")
            return sum_dist * distance_cost + sum_user_times * traveler_vot - assignment_reward

    elif func_key == "bike_rebalancing_objective":
        def control_f(simulation_time:float, veh_obj:SimulationVehicle, veh_plan:VehiclePlan, rq_dict:Dict[Any,PlanRequest], routing_engine:NetworkBase)->float:
            """This function evaluates the efficiency of bike rebalancing.
            The objective is to minimize empty vehicle kilometers and maximize bike collection efficiency.

            :param simulation_time: current simulation time
            :param veh_obj: simulation vehicle object
            :param veh_plan: vehicle plan in question
            :param rq_dict: rq -> Plan request dictionary
            :param routing_engine: for routing queries
            :return: objective function value
            """
            # Cost for distance traveled
            sum_dist = 0
            last_pos = veh_obj.pos
            for ps in veh_plan.list_plan_stops:
                pos = ps.get_pos()
                if pos != last_pos:
                    sum_dist += routing_engine.return_travel_costs_1to1(last_pos, pos)[2]
                    last_pos = pos
            
            current_load = len(veh_obj.pax)
            max_capacity = veh_obj.max_pax

            # Reward for successfully rebalancing bikes
            num_picked_up_bikes = 0
            num_dropped_off_bikes = 0
            
            # A set to keep track of requests that are picked up and then dropped off within this plan
            rebalanced_requests = set()
            picked_up_only_requests = set()

            for ps in veh_plan.list_plan_stops:
                # Get boarding and alighting request IDs
                boarding_rids = ps.get_list_boarding_rids()
                alighting_rids = ps.get_list_alighting_rids()

                for rid in boarding_rids:
                    if rid in rq_dict: # Ensure it's a request we care about
                        num_picked_up_bikes += 1
                        picked_up_only_requests.add(rid)
                
                for rid in alighting_rids:
                    if rid in rq_dict: # Ensure it's a request we care about
                        num_dropped_off_bikes += 1
                        if rid in picked_up_only_requests:
                            rebalanced_requests.add(rid)
                            picked_up_only_requests.remove(rid)
            
            # We want to reward fully completed rebalancing tasks
            reward_per_rebalanced_bike = 5000 # Example reward for completing a full rebalancing cycle (pickup + dropoff)
            penalty_for_uncompleted_pickup = 1000 # Example penalty for picking up but not dropping off in this plan
            
            # The objective function should be minimized.
            # So, distance is a positive cost.
            # Rewards are negative costs.
            # Penalties are positive costs.

            # Capacity considerations
            capacity_bonus = 0
            capacity_penalty = 0

            # If the vehicle is at maximum capacity and tries to pick up more bikes
            if current_load == max_capacity and num_picked_up_bikes > 0:
                capacity_penalty += num_picked_up_bikes * 10000 # Heavy penalty for overloading
            # If the vehicle is empty and picks up a bike
            elif current_load == 0 and num_picked_up_bikes > 0:
                capacity_bonus += num_picked_up_bikes * 500 # Bonus for starting to pick up when empty
            # If the vehicle has bikes and drops them off
            if current_load > 0 and num_dropped_off_bikes > 0:
                capacity_bonus += num_dropped_off_bikes * 500 # Bonus for offloading bikes
            
            objective_value = sum_dist \
                            - (len(rebalanced_requests) * reward_per_rebalanced_bike) \
                            + (len(picked_up_only_requests) * penalty_for_uncompleted_pickup) \
                            - capacity_bonus \
                            + capacity_penalty
                                    
            # Add a large penalty if no bikes are rebalanced but distance is covered
            # This encourages the drone to actually rebalance bikes if it moves
            if len(rebalanced_requests) == 0 and sum_dist > 0:
                objective_value += 10000 
                            
            return objective_value

    else:
        raise NotImplementedError(f"pooling objective function {func_key} not implemented! Please check the input parameter {G_OP_VR_CTRL_F}!")

    return control_f
