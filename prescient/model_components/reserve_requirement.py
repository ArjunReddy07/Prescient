#  ___________________________________________________________________________
#
#  Prescient
#  Copyright 2020 National Technology & Engineering Solutions of Sandia, LLC
#  (NTESS). Under the terms of Contract DE-NA0003525 with NTESS, the U.S.
#  Government retains certain rights in this software.
#  This software is distributed under the Revised BSD License.
#  ___________________________________________________________________________


## system variables and constraints
from __future__ import division
from pyomo.environ import *
import math
import six 

from prescient.model_components.decorators import add_model_attr 
component_name = 'reserve_requirement'

#TODO: this doesn't check if storage_services is added first, 
#      but this will only happen when there are storage_services!
@add_model_attr(component_name, requires = {'data_loader': None,
                                            'reserve_vars': None,
                                            'non_dispatchable_vars': None
                                            })
def CA_reserve_constraints(model):
    '''
    This is the reserve requirement with slacks given by equation (3) in

    Carrion, M. and Arroyo, J. (2006) A Computationally Efficient Mixed-Integer
    Liner Formulation for the Thermal Unit Commitment Problem. IEEE Transactions
    on Power Systems, Vol. 21, No. 3, Aug 2006.
    '''

    model.ReserveShortfall = Var(model.TimePeriods, within=NonNegativeReals)

    # the reserve shortfall can't be less than the reserve requirement in any given time period.
    def bound_reserve_shortfall_rule(m, t):
        return m.ReserveShortfall[t] <= m.ReserveRequirement[t]
    model.BoundReserveShortfall = Constraint(model.TimePeriods, rule=bound_reserve_shortfall_rule)


    # ensure there is sufficient maximal power output available to meet both the
    # demand and the spinning reserve requirements in each time period.
    # encodes Constraint 3 in Carrion and Arroyo.
    
    # IMPT: In contrast to power balance, reserves are (1) not per-bus and (2) expressed in terms of 
    #       maximum power available, and not actual power generated.
    
    def enforce_reserve_requirements_rule(m, t):
        if m.storage_services:
            return sum((1 - m.GeneratorForcedOutage[g,t]) * m.MaximumPowerAvailable[g, t] for g in m.ThermalGenerators) \
                 + sum((1-m.NondispatchableGeneratorForcedOutage[n,t]) * m.NondispatchablePowerUsed[n,t] for n in m.AllNondispatchableGenerators) \
                 + sum(m.PowerOutputStorage[s,t]*m.OutputEfficiencyEnergy[s] for s in m.Storage) \
                 - sum(m.PowerInputStorage[s,t] for s in m.Storage) \
                 + sum(m.LoadGenerateMismatch[b,t] for b in m.Buses) \
                 + m.ReserveShortfall[t] \
                 >= \
                 m.TotalDemand[t] + m.ReserveRequirement[t]
        else:
            return (sum((1 - m.GeneratorForcedOutage[g,t]) * m.MaximumPowerAvailable[g, t] for g in m.ThermalGenerators) \
                 + sum((1-m.NondispatchableGeneratorForcedOutage[n,t]) * m.NondispatchablePowerUsed[n,t] for n in m.AllNondispatchableGenerators) \
                 + sum(m.LoadGenerateMismatch[b,t] for b in m.Buses) \
                 + m.ReserveShortfall[t]) \
                 >= \
                 m.TotalDemand[t] + m.ReserveRequirement[t]
    
    model.EnforceReserveRequirements = Constraint(model.TimePeriods, rule=enforce_reserve_requirements_rule)

    return
## end carrion_reserve_constraints


## helper for reserve pricing problem
def _MLR_reserve_constraint(model):

    def enforce_reserve_requirements_rule(m, t):
        return sum((1 - m.GeneratorForcedOutage[g,t]) * m.ReserveProvided[g, t] for g in m.ThermalGenerators) \
                 + m.ReserveShortfall[t] \
                 >= \
                 m.ReserveRequirement[t]
    
    model.EnforceReserveRequirements = Constraint(model.TimePeriods, rule=enforce_reserve_requirements_rule)



@add_model_attr(component_name, requires = {'data_loader': None,
                                            'reserve_vars': None,
                                            })
def MLR_reserve_constraints(model):
    '''
    This is the reserve requirement with slacks given by equation (5) in
    
    G. Morales-Espana, J. M. Latorre, and A. Ramos. Tight and compact MILP
    formulation for the thermal unit commitment problem. IEEE Transactions on
    Power Systems, 28(4):4897–4908, 2013.
    '''
    model.ReserveShortfall = Var(model.TimePeriods, within=NonNegativeReals)

    # the reserve shortfall can't be less than the reserve requirement in any given time period.
    def bound_reserve_shortfall_rule(m, t):
        return m.ReserveShortfall[t] <= m.ReserveRequirement[t]
    model.BoundReserveShortfall = Constraint(model.TimePeriods, rule=bound_reserve_shortfall_rule)


    # ensure there is sufficient maximal power output available to meet both the
    # demand and the spinning reserve requirements in each time period.
    # encodes Constraint 3 in Carrion and Arroyo.
    
    # IMPT: In contrast to power balance, reserves are (1) not per-bus and (2) expressed in terms of 
    #       maximum power available, and not actual power generated.
    _MLR_reserve_constraint(model)

    return
## end carrion_reserve_constraints
