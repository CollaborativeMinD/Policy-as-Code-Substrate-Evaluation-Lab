"""One deterministic effect pattern with explicit target, onset, and recovery."""
from .contracts import ContractError, number

WOUNDS = {
    'traction_loss': dict(field='traction_fraction', location='inputs', mode='retain',
                          strategies=['ground'], unit='1'),
    'propulsor_loss': dict(field='thrust_n', location='parameters', mode='retain',
                          strategies=['vessel','spacecraft'], unit='N'),
    'rotor_loss': dict(field='max_thrust_n', location='parameters', mode='retain',
                      strategies=['rotorcraft'], unit='N'),
    'joint_derate': dict(field='torque_limits_nm', location='parameters', mode='retain',
                        strategies=['manipulator'], unit='N*m'),
    'array_loss': dict(field='array_power_w', location='parameters', mode='retain',
                      strategies=['spacecraft'], unit='W'),
    'cooling_loss': dict(field='heat_removal_w', location='parameters', mode='retain',
                        strategies=['containment'], unit='W'),
    'support_loss': dict(field='support_half_width_m', location='parameters', mode='retain',
                        strategies=['humanoid'], unit='m'),
    'thermal_rise': dict(field='temperature_c', location='inputs', mode='add', scale=40,
                        strategies=['compute'], unit='K'),
    'compute_delay': dict(field='latency_s', location='parameters', mode='add', scale=.5,
                         strategies=['compute','ground'], unit='s'),
    'rf_fade': dict(field='snr_db', location='inputs', mode='add', scale=-30,
                   strategies=['radar'], unit='dB'),
    'drag_growth': dict(field='drag_coefficient', location='inputs', mode='add', scale=.5,
                       strategies=['aircraft'], unit='1'),
    'engine_derate': dict(field='engine_thrust_n', location='parameters', mode='retain',
                         strategies=['launch'], unit='N'),
    'load_increase': dict(field='load_fraction', location='inputs', mode='toward_one',
                         strategies=['workload'], unit='1'),
    'elevation_mask': dict(field='elevation_deg', location='inputs', mode='toward_90',
                          strategies=['coverage'], unit='deg'),
}


def resolve_wounds(requests, strategies):
    if not isinstance(requests, (list, tuple)):
        raise ContractError('wounds must be a list')
    result = []; touched = set()
    allowed = {'id','severity','target','onset_s','rise_s','end_s','recovery_s'}
    for req in requests:
        if not isinstance(req, dict) or set(req)-allowed or not {'id','severity'} <= set(req):
            raise ContractError('wound needs id and severity; unknown keys are rejected')
        key = req['id']; target = req.get('target','substrate')
        if not isinstance(key,str) or not isinstance(target,str):
            raise ContractError('wound id and target must be strings')
        if key not in WOUNDS or target not in strategies:
            raise ContractError('unknown wound or target')
        spec = WOUNDS[key]
        if strategies[target] not in spec['strategies']:
            raise ContractError(f'{key} is incompatible with {target}')
        touch = (target,spec['location'],spec['field'])
        if touch in touched:
            raise ContractError('duplicate or conflicting effects on the same field')
        touched.add(touch)
        row = dict(id=key,target=target,definition=dict(spec))
        for k,default in [('severity',0),('onset_s',0),('rise_s',0),('recovery_s',0)]:
            row[k] = number(req.get(k,default),k,0,1 if k=='severity' else 1e8)
        row['end_s'] = None if req.get('end_s') is None else number(req['end_s'],'end_s',0,1e8)
        if row['end_s'] is not None and row['end_s'] < row['onset_s']+row['rise_s']:
            raise ContractError('end_s must follow onset plus rise')
        if row['end_s'] is None and row['recovery_s']:
            raise ContractError('recovery needs end_s')
        result.append(row)
    return sorted(result,key=lambda r:(r['target'],r['id']))


def severity_at(wound, time_s):
    onset = wound['onset_s']; rise = wound['rise_s']; end = wound['end_s']
    if time_s < onset:
        return 0.0
    factor = 1 if rise == 0 else min(1,(time_s-onset)/rise)
    if end is not None and time_s >= end:
        recovery = wound['recovery_s']
        factor = 0 if recovery == 0 else max(0,1-(time_s-end)/recovery)
    return wound['severity']*factor


def apply_effect(value, spec, severity):
    if isinstance(value,list):
        return [apply_effect(v,spec,severity) for v in value]
    mode = spec['mode']
    if mode == 'retain':
        return value*(1-severity)
    if mode == 'add':
        return value+severity*spec['scale']
    target = 1 if mode == 'toward_one' else 90
    return value+(target-value)*severity
