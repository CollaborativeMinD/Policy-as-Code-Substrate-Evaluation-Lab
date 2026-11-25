"""Explicit policy assessments and a synthetic workload state model."""
import math


def compute(p, x):
    t = x['temperature_c']; memory = x['memory_fraction']
    levels = [('TERMINAL_POLICY',p['terminal_c'],p['terminal_memory']),
              ('CONTINGENCY',p['contingency_c'],p['contingency_memory']),
              ('ALTERNATE',p['alternate_c'],p['alternate_memory'])]
    state = next((s for s,a,b in levels if t >= a or memory >= b),'NOMINAL')
    return {'policy_state': state, 'thermal_margin_k': p['terminal_c']-t,
            'memory_margin_fraction': p['terminal_memory']-memory,
            'loop_margin_s': p['loop_budget_s']-x['loop_time_s'],
            'queue_margin_items': p['queue_limit_items']-x['queue_items'],
            'estimated_latency_s': p['latency_s']+p['delay_s_per_k']*max(0,t-p['thermal_onset_c'])}


def workload(p, x):
    # Synthetic dimensionless state; no biological or diagnostic interpretation.
    decay = math.exp(-x['duration_s']/p['recovery_time_s'])
    equilibrium = p['load_gain']*x['load_fraction']
    state = x['initial_load']*decay+equilibrium*(-math.expm1(-x['duration_s']/p['recovery_time_s']))
    return {'synthetic_load_state': state, 'policy_margin': p['load_limit']-state}
