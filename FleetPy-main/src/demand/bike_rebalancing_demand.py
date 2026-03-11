import logging
import pandas as pd
import numpy as np

from src.demand.demand import Demand
from src.misc.globals import *
from src.demand.TravelerModels import RequestBase

LOG = logging.getLogger(__name__)

class BikeRebalancingDemand(Demand):
    """
    Demand class for bike rebalancing requests.
    """
    def __init__(self, scenario_parameters, output_f, routing_engine=None, zone_system=None):
        super().__init__(scenario_parameters, output_f, routing_engine, zone_system)
        self.misplaced_bikes_waiting_for_pickup = {} # Store bikes that are currently misplaced and need pickup
        self.misplaced_bikes_on_vehicle = {} # Store bikes that have been picked up and are on a vehicle
        LOG.debug(f"BikeRebalancingDemand initialized. Misplaced bikes waiting for pickup: {len(self.misplaced_bikes_waiting_for_pickup)}")

    def load_demand_file(self, start_time, end_time, rq_file_dir, rq_file_name, np_random_seed, rq_type=None,
                         rq_type_distr={}, rq_od_zone_distr={}, simulation_time_step=1):
        LOG.debug(f"Loading demand file: {rq_file_name} from {rq_file_dir}")
        super().load_demand_file(start_time, end_time, rq_file_dir, rq_file_name, np_random_seed, rq_type,
                                 rq_type_distr, rq_od_zone_distr, simulation_time_step)
        total_requests = sum(len(v) for v in self.future_requests.values())
        LOG.debug(f"After super().load_demand_file, total requests in self.future_requests: {total_requests}")
        LOG.info(f"Loaded {total_requests} bike rebalancing requests.")
        if total_requests > 0:
            # Log some details of the first few requests to verify they are loaded
            for time_key in sorted(self.future_requests.keys())[:5]:
                for i, (rid, request) in enumerate(self.future_requests[time_key].items()):
                    if i >= 2: break # Limit to first 2 requests per time key
                    LOG.debug(f"Sample request at time {time_key}: rid={rid}, start_pos={request.get_origin_pos()}")

    def get_new_travelers(self, simulation_time, *, since=None):
        """
        Overrides the base method to manage misplaced bikes.
        When a request becomes active, it's a 'misplaced bike' waiting for pickup.
        """
        LOG.debug(f"get_new_travelers called at sim_time: {simulation_time}, since: {since}")
        new_travelers = super().get_new_travelers(simulation_time, since=since)
        LOG.debug(f"super().get_new_travelers returned {len(new_travelers)} new travelers.")
        for rid, request in new_travelers:
            self.misplaced_bikes_waiting_for_pickup[rid] = request
            LOG.debug(f"Added new misplaced bike {rid} to waiting for pickup. Pos: {request.get_origin_pos()}")
        LOG.debug(f"Total misplaced bikes waiting for pickup: {len(self.misplaced_bikes_waiting_for_pickup)}")
        return new_travelers

    def get_misplaced_bikes_for_visualization(self):
        """
        Returns a dictionary of currently misplaced bikes (waiting for pickup or on vehicle)
        for visualization purposes.
        """
        # Combine bikes waiting for pickup and bikes currently on a vehicle
        return {**self.misplaced_bikes_waiting_for_pickup, **self.misplaced_bikes_on_vehicle}

    def get_undecided_travelers(self, sim_time):
        """
        Returns a list of (rid, Request) tuples for bikes waiting for pickup.
        This method is called by FleetSimulationBase for data collection.
        """
        return list(self.misplaced_bikes_waiting_for_pickup.items())

    # You might need to add methods here to handle pickup/dropoff logic for bikes.
    # For example, when a vehicle picks up a bike, move it from waiting_for_pickup to on_vehicle.
    # When a vehicle drops off a bike at a parking spot, remove it from on_vehicle.
