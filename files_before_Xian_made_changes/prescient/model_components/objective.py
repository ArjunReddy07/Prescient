## file for production cost functions
from __future__ import division
from pyomo.environ import *
import math
import six 

from prescient.model_components.decorators import add_model_attr 
component_name = 'objective'

def _compute_1bin_shutdown_costs(model):
    #############################################################
    # compute the per-generator, per-time period shutdown costs #
    #############################################################
    
    def compute_shutdown_costs_rule(m, g, t):
        if t == m.InitialTime:
          return m.ShutdownCost[g, t] >= m.ShutdownFixedCost[g] * (m.UnitOnT0[g] - m.UnitOn[g, t])
        else:
          return m.ShutdownCost[g, t] >= m.ShutdownFixedCost[g] * (m.UnitOn[g, t-1] - m.UnitOn[g, t])
    
    model.ComputeShutdownCosts = Constraint(model.ThermalGenerators, model.TimePeriods, rule=compute_shutdown_costs_rule)

def _1bin_shutdown_costs(model, add_shutdown_cost_var=True):

    if add_shutdown_cost_var:
        model.ShutdownCost = Var(model.ThermalGenerators, model.TimePeriods, within=NonNegativeReals)

    _compute_1bin_shutdown_costs(model)

def _3bin_shutdown_costs(model, add_shutdown_cost_var=True):

    #############################################################
    # compute the per-generator, per-time period shutdown costs #
    #############################################################
    ## BK -- replaced with UnitStop

    if add_shutdown_cost_var:
        model.ShutdownCost = Var(model.ThermalGenerators, model.TimePeriods, within=Reals)
    
    def compute_shutdown_costs_rule(m, g, t):
        return m.ShutdownCost[g,t] ==  m.ShutdownFixedCost[g] * (m.UnitStop[g, t])
    
    model.ComputeShutdownCosts = Constraint(model.ThermalGenerators, model.TimePeriods, rule=compute_shutdown_costs_rule)

def _add_shutdown_costs(model, add_shutdown_cost_var=True):
    #NOTE: we handle shutdown costs in this manner because it's not a 
    #      common point of contention in the literature, and they're 
    #      often zero as is.
    if model.status_vars in ['garver_3bin_vars','garver_3bin_relaxed_stop_vars','garver_2bin_vars', 'ALS_state_transition_vars']:
        _3bin_shutdown_costs(model, add_shutdown_cost_var)
    elif model.status_vars in ['CA_1bin_vars',]:
        _1bin_shutdown_costs(model, add_shutdown_cost_var)
    else:
        raise Exception("Problem adding shutdown costs, cannot identify status_vars for this model")
    

#TODO: this doesn't check if regulation_services is added first, 
#      but this will only happen when there are regulation_services!
@add_model_attr(component_name, requires = {'data_loader': None,
                                            'status_vars': ['garver_3bin_vars', 'CA_1bin_vars', 'garver_2bin_vars', 'garver_3bin_relaxed_stop_vars', 'ALS_state_transition_vars'],
                                            'power_vars': None,
                                            'startup_costs': None,
                                            'production_costs': None,
                                            'power_balance': None,
                                            'reserve_requirement': None,
                                            })
def basic_objective(model):
    '''
    adds the objective and shutdown cost formulation to the model
    '''
    
    #############################################
    # constraints for computing cost components #
    #############################################
    
    def compute_total_no_load_cost_rule(m,t):
        return sum(m.MinimumProductionCost[g]*m.UnitOn[g,t]*m.TimePeriodLengthHours for g in m.ThermalGenerators)
    
    model.TotalNoLoadCost = Expression(model.TimePeriods, rule=compute_total_no_load_cost_rule)
    
    _add_shutdown_costs(model)

    # 
    # Cost computations
    #
    
    def commitment_stage_cost_expression_rule(m, st):
        cc = sum(m.StartupCost[g,t] + m.ShutdownCost[g,t] for g in m.ThermalGenerators for t in m.CommitmentTimeInStage[st]) + \
             sum(m.TotalNoLoadCost[t] for t in m.CommitmentTimeInStage[st])
        if m.ancillary_services:
            cc += sum(m.RegulationCostCommitment[g,t] for g in m.ThermalGenerators for t in m.CommitmentTimeInStage[st])
        return cc
    
    model.CommitmentStageCost = Expression(model.StageSet, rule=commitment_stage_cost_expression_rule)

    def compute_load_mismatch_cost_rule(m, t):
        return m.LoadMismatchPenalty*m.TimePeriodLengthHours*sum(m.posLoadGenerateMismatch[b, t] + m.negLoadGenerateMismatch[b, t] for b in m.Buses) 
    model.LoadMismatchCost = Expression(model.TimePeriods, rule=compute_load_mismatch_cost_rule)

    def compute_reserve_shortfall_cost_rule(m, t):
        return m.ReserveShortfallPenalty*m.TimePeriodLengthHours*m.ReserveShortfall[t]
    model.ReserveShortfallCost = Expression(model.TimePeriods, rule=compute_reserve_shortfall_cost_rule)
    
    def generation_stage_cost_expression_rule(m, st):
        ## NOTE: Production and Load/Reserve penalites are multiplied by time here, and not when constructed
        cc = sum(m.ProductionCost[g, t] for g in m.ThermalGenerators for t in m.GenerationTimeInStage[st]) + \
              sum(m.LoadMismatchCost[t] for t in m.GenerationTimeInStage[st]) + \
              sum(m.ReserveShortfallCost[t] for t in m.GenerationTimeInStage[st])
        if m.ancillary_services:
            cc += sum(m.RegulationCostGeneration[g,t] for g in m.ThermalGenerators for t in m.GenerationTimeInStage[st]) \
                + sum(m.RegulationCostPenalty[t] for t in m.GenerationTimeInStage[st]) \
                + \
                  sum(m.SpinningReserveCostGeneration[g,t] for g in m.ThermalGenerators for t in m.GenerationTimeInStage[st]) \
                + sum(m.SpinningReserveCostPenalty[t] for t in m.GenerationTimeInStage[st]) \
                + \
                  sum(m.NonSpinningReserveCostGeneration[g,t] for g in m.ThermalGenerators for t in m.GenerationTimeInStage[st]) \
                + sum(m.NonSpinningReserveCostPenalty[t] for t in m.GenerationTimeInStage[st]) \
                + \
                  sum(m.OperatingReserveCostGeneration[g,t] for g in m.ThermalGenerators for t in m.GenerationTimeInStage[st]) \
                + sum(m.OperatingReserveCostPenalty[t] for t in m.GenerationTimeInStage[st]) \
                + \
                  sum(m.FlexibleRampingCostPenalty[t] for t in m.GenerationTimeInStage[st])
        return cc
    model.GenerationStageCost = Expression(model.StageSet, rule=generation_stage_cost_expression_rule)
    
    def stage_cost_expression_rule(m, st):
        return m.GenerationStageCost[st] + m.CommitmentStageCost[st]
    model.StageCost = Expression(model.StageSet, rule=stage_cost_expression_rule)
    
    #
    # Objectives
    #
    
    def total_cost_objective_rule(m):
       return sum(m.StageCost[st] for st in m.StageSet)	
    
    model.TotalCostObjective = Objective(rule=total_cost_objective_rule, sense=minimize)

    return
