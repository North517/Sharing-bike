import logging
import importlib
import os
import json

from src.FleetSimulationBase import FleetSimulationBase

from src.misc.globals import *
LOG = logging.getLogger(__name__)

INPUT_PARAMETERS_ImmediateDecisionsSimulation = {
    "doc" : "in this simulation each request immediatly decides for or against an offer",
    "inherit" : "FleetSimulationBase",
    "input_parameters_mandatory": [],
    "input_parameters_optional": [],
    "mandatory_modules": [], 
    "optional_modules": []
}


class ImmediateDecisionsSimulation(FleetSimulationBase):
    """
    Init main simulation module. Check the documentation for a flowchart of this particular simulation environment.
    Main attributes:
    - agent list per time step query public transport and fleet operator for offers and immediate decide
    - fleet operator offers ride pooling service
    - division of study area
        + first/last mile service in different parts of the study area
        + different parking costs/toll/subsidy in different parts of the study area
    """

    def check_sim_env_spec_inputs(self, scenario_parameters):
        if scenario_parameters[G_AR_MAX_DEC_T] != 0:
            raise EnvironmentError(f"Scenario parameter {G_AR_MAX_DEC_T} has to be set to 0 for simulations in the "
                                   f"{self.__class__.__name__} environment!")

    def add_init(self, scenario_parameters):
        super().add_init(scenario_parameters)

    def step(self, sim_time):
        self.update_sim_state_fleets(sim_time - self.time_step, sim_time)
        new_travel_times = self.routing_engine.update_network(sim_time)
        if new_travel_times:
            self.broker.inform_network_travel_time_update(sim_time)

        list_undecided_travelers = list(self.demand.get_undecided_travelers(sim_time))
        last_time = sim_time - self.time_step
        if last_time < self.start_time:
            last_time = None
        
        processed_new_travelers = []
        for rid, rq_obj in self.demand.get_new_travelers(sim_time, since=last_time):
            processed_new_travelers.append((rid, rq_obj))

        for rid, rq_obj in processed_new_travelers:
            self.broker.inform_request(rid, rq_obj, sim_time)
            amod_offers = self.broker.collect_offers(rid)
            for op_id, amod_offer in amod_offers.items():
                rq_obj.receive_offer(op_id, amod_offer, sim_time)
            self._rid_chooses_offer(rid, rq_obj, sim_time)
            self.demand.remove_undecided_request(rid)

        for rid, rq_obj in list_undecided_travelers:
            if rid not in self.demand.undecided_rq:
                continue
            self.broker.inform_request(rid, rq_obj, sim_time)
            amod_offers = self.broker.collect_offers(rid)
            for op_id, amod_offer in amod_offers.items():
                rq_obj.receive_offer(op_id, amod_offer, sim_time)
            self._rid_chooses_offer(rid, rq_obj, sim_time)
            self.demand.remove_undecided_request(rid)

        self._check_waiting_request_cancellations(sim_time)

        for op in self.operators:
            op.time_trigger(sim_time)

        for ch_op_dict in self.charging_operator_dict.values():
            for ch_op in ch_op_dict.values():
                ch_op.time_trigger(sim_time)

        self.record_stats()

    def add_evaluate(self):
        pass

    # ✅ 修复：缺失方法 1 → _rid_chooses_offer
    def _rid_chooses_offer(self, rid, rq_obj, sim_time):
        chosen_operator = rq_obj.choose_offer(self.scenario_parameters, sim_time)
        if chosen_operator is None:
            if rq_obj.leaves_system(sim_time):
                self._user_leaves_system(rid, sim_time)
            else:
                self.demand.undecided_rq[rid] = rq_obj
        elif chosen_operator == -1:
            self._user_leaves_system(rid, sim_time)
        else:
            amode_confirmed_rids = self.broker.inform_user_booking(rid, rq_obj, sim_time, chosen_operator)
            for rid, rq_obj in amode_confirmed_rids:
                self.demand.waiting_rq[rid] = rq_obj
            try:
                del self.demand.undecided_rq[rid]
            except KeyError:
                pass

    # ✅ 修复：缺失方法 2 → _user_leaves_system
    def _user_leaves_system(self, rid, sim_time):
        self.broker.inform_user_leaving_system(rid, sim_time)
        self.demand.record_user(rid)
        try:
            del self.demand.rq_db[rid]
            del self.demand.undecided_rq[rid]
        except KeyError:
            pass

    # ✅ 修复：修正请求对象属性调用
    def _check_waiting_request_cancellations(self, sim_time):
        to_delete = []
        for rid, rq_obj in self.demand.waiting_rq.items():
            # 修正：使用属性而不是方法
            chosen_op = rq_obj.chosen_operator_id
            # 修正：使用属性而不是方法
            in_veh = rq_obj.service_vid
            if in_veh is None and chosen_op is not None:
                if rq_obj.cancels_booking(sim_time):
                    self.broker.inform_waiting_request_cancellations(chosen_op, rid, sim_time)
                    self.demand.record_user(rid)
                    to_delete.append(rid)
        for rid in to_delete:
            try:
                del self.demand.rq_db[rid]
                del self.demand.waiting_rq[rid]
            except KeyError:
                pass