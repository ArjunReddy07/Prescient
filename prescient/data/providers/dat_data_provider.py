#  ___________________________________________________________________________
#
#  Prescient
#  Copyright 2020 National Technology & Engineering Solutions of Sandia, LLC
#  (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
#  Government retains certain rights in this software.
#  This software is distributed under the Revised BSD License.
#  ___________________________________________________________________________
from __future__ import annotations

from ..data_provider import DataProvider
from egret.parsers.prescient_dat_parser import get_uc_model, create_model_data_dict_params
from egret.data.model_data import ModelData as EgretModel
import os.path
from datetime import datetime, date, timedelta
import dateutil.parser
import copy

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from prescient.simulator.options import Options
    from typing import Dict, Any

class DatDataProvider():
    ''' Provides data from pyomo DAT files
    '''

    def initialize(self, options: Options) -> None:
        ''' Do one-time initial setup
        '''
        self._uc_model_template = get_uc_model()
        self._instance_directory_name = os.path.join(os.path.expanduser(options.data_directory), 
                                                     "pyspdir_twostage")
        self._actuals_by_date = {}
        self._forecasts_by_date = {}
        self._first_day = dateutil.parser.parse(options.start_date).date()
        self._final_day = self._first_day + timedelta(days=options.num_days-1)

    def get_initial_model(self, options:Options, num_time_steps:int) -> EgretModel:
        ''' Get a model ready to be populated with data

        Returns
        -------
        A model object populated with static system information, such as
        buses and generators, and with time series arrays that are large
        enough to hold num_time_steps entries.

        Initial values in time time series do not have meaning.
        '''
        # Get data for the first simulation day
        first_day_model = self._get_forecast_by_date(self._first_day)

        # Copy it, making sure we've got the right number of time periods
        data =_recurse_copy_with_time_series_length(first_day_model.data, num_time_steps)
        new_model = EgretModel(data)
        new_model.data['system']['time_keys'] = list(str(i) for i in range(1,num_time_steps+1))

        return new_model

    def populate_initial_state_data(self, options:Options,
                                    day:date,
                                    model: EgretModel) -> None:
        ''' Populate an existing model with initial state data for the requested day

        Sets T0 information from actuals:
          * initial_state_of_charge for each storage element
          * initial_status for each generator
          * initial_p_output for each generator

        Arguments
        ---------
        options:
            Option values
        day:date
            The day whose initial state will be saved in the model
        model: EgretModel
            The model whose values will be modifed
        '''
        if day < self._first_day:
            day = self._first_day
        elif day > self._final_day:
            day = self._final_day

        actuals = self._get_actuals_by_date(day)

        for s, sdict in model.elements('storage'):
            soc = actuals.data['elements']['storage'][s]['initial_state_of_charge']
            sdict['initial_state_of_charge'] = soc

        for g, gdict in model.elements('generator', generator_type='thermal'):
            source = actuals.data['elements']['generator'][g]
            gdict['initial_status'] = source['initial_status']
            gdict['initial_p_output'] = source['initial_p_output']


    def populate_with_forecast_data(self, options:Options,
                                    start_time:datetime,
                                    num_time_periods: int,
                                    time_period_length_minutes: int,
                                    model: EgretModel
                                   ) -> None:
        ''' Populate an existing model with forecast data.

        Populates the following values for each requested time period:
            * demand for each bus
            * min and max non-dispatchable power for each non-dispatchable generator
            * reserve requirement
            
        Arguments
        ---------
        options:
            Option values
        start_time: datetime
            The time (day, hour, and minute) of the first time step for
            which forecast data will be provided
        num_time_periods: int
            The number of time steps for which forecast data will be provided.
        time_period_length_minutes: int
            The number of minutes between each time step
        model: EgretModel
            The model where forecast data will be stored

        Notes
        -----
        This will store forecast data in the model's existing data arrays, starting
        at index 0.  If the model's arrays are not big enough to hold all the
        requested time steps, only those steps for which there is sufficient storage
        will be saved.  If arrays are larger than the number of requested time 
        steps, the remaining array elements will be left unchanged.

        Forecast data is always taken from the file matching the date of the forecast.
        In other words, only the first 24 hours of each forecast file will ever be
        used.  If this isn't what you want, you'll need to handle that yourself.

        Note that this method has the same signature as populate_with_actuals.
        '''
        self._populate_with_forecastable_data(options, start_time, num_time_periods,
                                              time_period_length_minutes, model,
                                              self._get_forecast_by_date)

    def populate_with_actuals(self, options:Options,
                              start_time:datetime,
                              num_time_periods: int,
                              time_period_length_minutes: int,
                              model: EgretModel
                             ) -> None:
        ''' Populate an existing model with actual values.

        Populates the following values for each requested time period:
            * demand for each bus
            * min and max non-dispatchable power for each non-dispatchable generator
            * reserve requirement
            
        Arguments
        ---------
        options:
            Option values
        start_time: datetime
            The time (day, hour, and minute) of the first time step for
            which actual data will be provided
        num_time_periods: int
            The number of time steps for which actual data will be provided.
        time_period_length_minutes: int
            The number of minutes between each time step
        model: EgretModel
            The model where actuals data will be stored

        Notes
        -----
        This will store actuals data in the model's existing data arrays, starting
        at index 0.  If the model's arrays are not big enough to hold all the
        requested time steps, only those steps for which there is sufficient storage
        will be saved.  If arrays are larger than the number of requested time 
        steps, the remaining array elements will be left unchanged.

        Actuals data is always taken from the file matching the date of the time step.
        In other words, only the first 24 hours of each actuals file will ever be
        used.  If this isn't what you want, you'll need to handle that yourself.

        Note that this method has the same signature as populate_with_actuals.
        '''
        self._populate_with_forecastable_data(options, start_time, num_time_periods,
                                              time_period_length_minutes, model,
                                              self._get_actuals_by_date)

    def _populate_with_forecastable_data(self, options:Options,
                                         start_time:datetime,
                                         num_time_periods: int,
                                         time_period_length_minutes: int,
                                         model: EgretModel,
                                         identify_dat: Callable[[date], EgretModel]
                                        ) -> None:
        # For now, require the time period to always be 60 minutes
        assert(time_period_length_minutes == 60.0)
        step_delta = timedelta(minutes=time_period_length_minutes)

        # See if we have space to store all the requested data.
        # If not, only supply what we have space for
        if len(model.data['system']['time_keys']) < num_time_periods:
            num_time_periods = len(model.data['system']['time_keys'])

        # Collect a list of non-dispatchable generators
        renewables = list(model.elements('generator', generator_type='renewable'))

        start_hour = start_time.hour
        start_day = start_time.date()

        # Loop through each time step
        for step_index in range(0, num_time_periods):
            step_time = start_time + step_delta*step_index
            day = step_time.date()

            # 0-based hour, useable as index into forecast arrays
            hour = step_time.hour

            # For data starting at time 0, we collect tomorrow's data
            # from today's dat file
            if start_hour == 0 and day != start_day:
                day = start_day
                hour += 24

            # If request is beyond the last day, just repeat the final day's values
            if day > self._final_day:
                day = self._final_day

            dat = identify_dat(day)

            # fill in renewables limits
            for gen, gdata in renewables:
                pmin = dat.data['elements']['generator'][gen]['p_min']['values'][hour]
                pmax = dat.data['elements']['generator'][gen]['p_max']['values'][hour]
                gdata['p_min']['values'][step_index] = pmin
                gdata['p_max']['values'][step_index] = pmax

            # Fill in load data
            for bus, bdata in model.elements('load'):
                load = dat.data['elements']['load'][bus]['p_load']['values'][hour]
                bdata['p_load']['values'][step_index] = load

            # Fill in reserve data
            reserve_req = dat.data['system']['reserve_requirement']['values'][hour]
            model.data['system']['reserve_requirement']['values'][step_index] = reserve_req


    def _get_forecast_by_date(self, requested_date: date) -> EgretModel:
        ''' Get forecast data for a specific calendar day.
        '''
        return self._get_egret_model_for_date(requested_date, 
                                              "Scenario_forecasts.dat", 
                                              self._forecasts_by_date)

    def _get_actuals_by_date(self, requested_date: date) -> EgretModel:
        ''' Get actuals data for a specific calendar day.
        '''
        return self._get_egret_model_for_date(requested_date, 
                                              "Scenario_actuals.dat", 
                                              self._actuals_by_date)

    def _get_egret_model_for_date(self, 
                                  requested_date: date, 
                                  dat_filename: str,
                                  cache_dict: Dict[date, EgretModel]) -> EgretModel:
        ''' Get data for a specific calendar day.

            Implements the common logic of _get_actuals_by_date and _get_forecast_by_date.
        '''
        # Return cached model, if we have it
        if requested_date in cache_dict:
            return cache_dict[requested_date]

        # Otherwise read the requested data and store it in the cache
        date_str = str(requested_date)
        path_to_dat = os.path.join(self._instance_directory_name,
                                   date_str,
                                   dat_filename)

        day_pyomo = self._uc_model_template.create_instance(path_to_dat)
        day_dict = create_model_data_dict_params(day_pyomo, True)
        day_model = EgretModel(day_dict)
        cache_dict[requested_date] = day_model

        return day_model

def _recurse_copy_with_time_series_length(root:Dict[str, Any], time_count:int) -> Dict[str, Any]:
    new_node = {}
    for key, att in root.items():
        if isinstance(att, dict):
            if 'data_type' in att and att['data_type'] == 'time_series':
                val = att['values'][0]
                new_node[key] = { 'data_type': 'time_series',
                                  'values' : [val]*time_count }
            else:
                new_node[key] = _recurse_copy_with_time_series_length(att, time_count)
        else:
            new_node[key] = copy.deepcopy(att)
    return new_node
