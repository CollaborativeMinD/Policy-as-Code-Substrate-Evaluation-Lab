"""One adapter dispatches native quantities and produces an explicit receipt."""
from copy import deepcopy
from . import mechanics, fields, response
from .contracts import ContractError, number, validate
from .wounds import apply_effect, severity_at

STRATEGIES = {name:getattr(module,name) for module,names in [
    (mechanics,['ground','vessel','aircraft','rotorcraft','humanoid','manipulator','launch']),
    (fields,['radar','coverage','spacecraft','containment']),
    (response,['compute','workload'])] for name in names}


def modify(data, params, values, target, time_s):
    applied = []
    for wound in data['wounds']:
        if wound['target'] != target:
            continue
        effect = wound['definition']; severity = severity_at(wound,time_s)
        mapping = params if effect['location']=='parameters' else values
        key = effect['field']; before = mapping[key]
        mapping[key] = apply_effect(before,effect,severity)
        applied.append(dict(wound=wound['id'],target=target,field=key,unit=effect['unit'],
                            severity=severity,before=before,after=mapping[key]))
    return applied


def run(profile, params, values):
    validate(profile['inputs'],values)
    bounds=deepcopy(profile['parameters'])
    zero_capabilities={'thrust_n','max_thrust_n','torque_limits_nm','array_power_w',
                       'heat_removal_w','support_half_width_m','engine_thrust_n'}
    for field in bounds:
        if field['name'] in zero_capabilities:field['lower']=0
    validate(bounds,params)
    if profile['strategy']=='radar' and values['bandwidth_hz']>values['frequency_hz']:
        raise ContractError('bandwidth exceeds carrier; this narrowband lesson is inapplicable')
    result = STRATEGIES[profile['strategy']](params,values)
    for key,value in result.items():
        if key not in profile['outputs']:
            raise ContractError(f'undeclared output: {key}')
        if value is None or isinstance(value,str):
            continue
        for component in value if isinstance(value,list) else [value]:
            number(component,key,-1e100,1e100)
    if result.get('temperature_k',1)<0:
        raise ContractError('linear cooling extrapolated below absolute zero; shorten the horizon')
    return result


def evaluate(config, observations, *, time_s=0):
    from .registry import import_configuration
    data = config.to_dict()
    import_configuration(data)
    time_s = number(time_s,'time_s',0,1e8)
    if not isinstance(observations,dict):
        raise ContractError('observations must be an object')
    raw = deepcopy(observations); board_values = raw.pop('compute',None)
    profile = data['substrate']; params = dict(data['parameters'])
    values = validate(profile['inputs'],raw)
    applied = modify(data,params,values,'substrate',time_s)
    board_result = None
    if 'compute' in data:
        board = data['compute']; bp = dict(data['compute_parameters'])
        bx = validate(board['inputs'],board_values)
        applied += modify(data,bp,bx,'compute',time_s)
        board_result = run(board,bp,bx)
        if data['coupling']=='ground_stopping_latency':
            params['latency_s'] += board_result['estimated_latency_s']
    elif board_values is not None:
        raise ContractError('compute observations without a compute component')
    result = run(profile,params,values)
    exceeded = [k for k,v in result.items() if 'margin' in k and isinstance(v,(float,int)) and v<0]
    if board_result:
        exceeded += ['compute.'+k for k,v in board_result.items() if 'margin' in k and v<0]
    unavailable = profile['strategy']=='ground' and result['stopping_distance_m'] is None
    disposition = 'CAPABILITY_LOST' if unavailable else 'LIMIT_EXCEEDED' if exceeded else 'WITHIN_DECLARED_MODEL'
    if disposition == 'WITHIN_DECLARED_MODEL' and any(
            r.get('policy_state','NOMINAL')!='NOMINAL' for r in [result,board_result or {}]):
        disposition = 'POLICY_DEGRADED'
    return dict(config_hash=config.digest,catalog_hash=data['catalog_hash'],
                implementation_hash=data['implementation_hash'],source_index_hash=data['source_index_hash'],time_s=time_s,
                disposition=disposition,exceeded=exceeded,metrics=result,units=profile['outputs'],
                effective_parameters=params,effective_inputs=values,applied_wounds=applied,
                compute=board_result,coupling=data.get('coupling','none'),fidelity=profile['fidelity'],
                observations=deepcopy(observations),
                parameter_provenance={f['name']: ('USER_SUPPLIED' if f['name'] in data['overrides'] else f['basis']) for f in profile['parameters']},
                interpretation='Model assessment only; no operational authority or calibrated probability.')
