#  ___________________________________________________________________________
#
#  Prescient
#  Copyright 2020 National Technology & Engineering Solutions of Sandia, LLC
#  (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
#  Government retains certain rights in this software.
#  This software is distributed under the Revised BSD License.
#  ___________________________________________________________________________

from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import TypeVar, Iterable, Optional, Mapping, Tuple, Union
    from .abstract_types import *
    from prescient.simulator.options import Options
    from .data_extractors import ScedDataExtractor, RucDataExtractor

from abc import ABC, abstractmethod
from enum import Enum, auto

class ForecastErrorMethod(Enum):
    PRESCIENT = auto()
    PERSISTENT = auto()

class ModelingEngine(ABC):
    '''
    Provides model manipulation and solving capabilities
    '''

    @abstractmethod
    def initialize(self, options:Options) -> None:
        pass

    @abstractmethod
    def create_deterministic_ruc(self,
            options: Options,
            uc_date:str,
            uc_hour: int,
            prior_ruc_instance: RucModel,
            output_ruc_initial_conditions: bool,
            projected_sced_instance: OperationsModel,
            sced_schedule_hour: int,
            ruc_horizon: int,
            run_ruc_with_next_day_data: bool
           ) -> RucModel:
        pass

    @abstractmethod
    def solve_deterministic_ruc(self,
            options: Options,
            ruc_instance: RucModel,
            uc_date:str,
            uc_hour: int
           ) -> RucModel:
        pass


    @abstractmethod
    def create_simulation_actuals(
            self,
            options: Options,
            uc_date: str,
            uc_hour: int
           ) -> RucModel:
        ''' Get a new model holding data to be treated as actuals, starting at a given time.

        Parameters
        ----------
        options:Options
            Global option values
        data_provider: DataProvider
            An object that can provide actual and/or forecast data for the requested days
        this_date: string
            A string that can be parsed as a date
        this_hour: int
            0-based index of the first hour of the day for which data should be retrieved
        ''' 
        pass


    @abstractmethod
    def create_sced_instance(self,
            deterministic_ruc_instance_for_this_period: RucModel,
            deterministic_ruc_instance_for_next_period: RucModel,
            ruc_instance_to_simulate_this_period: RucModel,
            prior_sced_instance: OperationsModel,
            actual_demand: Mapping[Tuple[Bus, int], float],
            demand_forecast_error: Mapping[Tuple[Bus, int], float],
            actual_min_renewables: Mapping[Tuple[Generator, int], float],
            actual_max_renewables: Mapping[Tuple[Generator, int], float],
            renewables_forecast_error: Mapping[Tuple[Generator, int], float],
            hour_to_simulate: int,
            reserve_factor: float,
            options: Options,
            hours_in_objective: int=1,
            sced_horizon: int=24,
            ruc_every_hours: int=24,
            initialize_from_ruc: bool=True,
            forecast_error_method: ForecastErrorMethod=ForecastErrorMethod.PRESCIENT,
            write_sced_instance: bool = False,
            output_initial_conditions: bool = False,
            output_demands: bool = False
            ) -> OperationsModel:
        '''
        Create a new operations model.

        Although the last three arguments are present in the options argument, they should not be taken 
        directly from that object.  That is because they only apply to a "normal" sced, not a projected 
        sced, and this method is called for both (and could conceivably be called for other purposes as
        well).  The engine doesn't have any context to know which type of sced is being requested.

        Returns
        -------
        The operations model, ready to be solved.
        '''
        pass

    @abstractmethod
    def solve_sced_instance(self, 
                            options: Options, 
                            sced_instance: OperationsModel, 
                            output_initial_conditions: bool = False, 
                            output_demands: bool = False,
                            lp_filename: str = None
            ) -> Tuple[OperationsModel, float]:
        '''
        Solves an operations model.

        Although the output_* arguments are present in the options argument, they should not be taken 
        directly from that object.  That is because they only apply to a "normal" sced, not a projected 
        sced, and this method is called for both (and could conceivably be called for other purposes as
        well).  The engine doesn't have any context to know which type of sced is being requested.

        Returns
        -------
        The operations model with results, and the solve time in seconds.
        '''
        pass

    def enable_quickstart_and_solve(self,
            sced_instance: OperationsModel,
            options: Options
           ) -> OperationsModel:
        '''
        Re-solve the passed in model with quickstart generators enabled.  The existing model 
        is allowed to be modified in-place rather than creating a new model if it is efficient
        to do so.  The returned model may be the existing model with quick start modifications
        and results, or it may be a new model.
        '''
        pass


    @abstractmethod
    def create_and_solve_lmp(self,
            sced_instance: OperationsModel,
            options:Options,
           ) -> OperationsModel:
        '''
        Create and solve a variation of the passed in model that honors price thesholds
        '''
        pass

    @property
    @abstractmethod
    def ruc_data_extractor(self) -> RucDataExtractor:
        ''' An object that extracts statistics from a RUC model '''
        pass

    @property
    @abstractmethod
    def operations_data_extractor(self) -> ScedDataExtractor:
        ''' An object that extracts statistics from a solved operations model '''
        pass
