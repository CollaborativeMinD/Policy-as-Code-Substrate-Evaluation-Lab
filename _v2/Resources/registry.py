"""Single catalog and configuration resolver for humans and agents."""
from pathlib import Path
from hashlib import sha256
import json
from .contracts import ContractError, ResolvedConfiguration, canonical, validate
from .wounds import resolve_wounds
from .identity import implementation_hash

ROOT = Path(__file__).resolve().parent


def catalog():
    return json.loads((ROOT/'catalog.json').read_text())


def select(identity):
    if not isinstance(identity,str):
        raise ContractError('substrate identity must be a string')
    if any(identity in p.get('retired_ambiguous_aliases',[]) for p in catalog()):
        raise ContractError('ambiguous TI hybrid identity: select an explicit TDA4VM, AI-64, or AM68A record')
    matches = [p for p in catalog() if identity == p['id'] or identity in p['aliases']]
    if len(matches) != 1:
        raise ContractError(f'unknown or ambiguous substrate: {identity!r}')
    return matches[0]


def parameters(profile, overrides):
    values = {f['name']:f['default'] for f in profile['parameters']}
    values.update(validate(profile['parameters'],overrides,complete=False))
    validate(profile['parameters'],values)
    if profile['strategy'] == 'compute':
        for fields in [('alternate_c','contingency_c','terminal_c'),
                       ('alternate_memory','contingency_memory','terminal_memory')]:
            if not values[fields[0]] < values[fields[1]] < values[fields[2]]:
                raise ContractError('compute policy thresholds must strictly increase')
    return values


def compose(substrate, *, wounds=(), compute=None, overrides=None, compute_overrides=None,
            source_payload=None, source_ref=None):
    profile = select(substrate)
    if compute_overrides is not None and not isinstance(compute_overrides,dict):
        raise ContractError('compute_overrides must be an object')
    if source_ref is not None and (not isinstance(source_ref,str) or not source_ref.strip()):
        raise ContractError('source_ref must be a nonempty string')
    overrides = {} if overrides is None else overrides
    if source_payload is not None:
        if profile['strategy'] != 'manipulator' or not isinstance(source_ref,str) or not source_ref.strip():
            raise ContractError('Panda payload requires a nonempty source_ref')
        from .replay import panda_parameters
        incoming = panda_parameters(source_payload)
        if set(incoming)&set(overrides):
            raise ContractError('payload and override conflict')
        overrides = dict(overrides,**incoming)
    p = parameters(profile,overrides)
    data = dict(schema='hmt.substrate.config.v2',catalog_version='2.0.0',
                substrate=profile,parameters=p,overrides=overrides,
                source_ref=source_ref,source_payload=source_payload)
    strategies = {'substrate':profile['strategy']}
    if compute is not None:
        if profile['strategy'] == 'compute':
            raise ContractError('a compute profile cannot contain another compute component')
        board = select(compute)
        if board['strategy'] != 'compute':
            raise ContractError('compute component must use the compute strategy')
        data['compute'] = board
        data['compute_parameters'] = parameters(board,compute_overrides or {})
        strategies['compute'] = 'compute'
        data['coupling'] = 'ground_stopping_latency' if profile['strategy']=='ground' else 'parallel_assessment'
    elif compute_overrides:
        raise ContractError('compute_overrides requires a compute component')
    data['wounds'] = resolve_wounds(wounds,strategies)
    data['catalog_hash'] = sha256(canonical(catalog()).encode()).hexdigest()
    data['implementation_hash'] = implementation_hash()
    data['source_index_hash'] = sha256((ROOT/'sources.json').read_bytes()).hexdigest()
    return ResolvedConfiguration(canonical(data))


def example(config):
    data = config.to_dict()
    values = {f['name']:f['default'] for f in data['substrate']['inputs']}
    if 'compute' in data:
        values['compute'] = {f['name']:f['default'] for f in data['compute']['inputs']}
    return values


def import_configuration(document):
    if not isinstance(document,dict) or document.get('schema') != 'hmt.substrate.config.v2':
        raise ContractError('unsupported configuration schema')
    result = compose(document['substrate']['id'], wounds=[
        {k:v for k,v in w.items() if k!='definition'} for w in document['wounds']],
        compute=document.get('compute',{}).get('id'),overrides={
            k:v for k,v in document['overrides'].items()
            if not(document.get('source_payload') and k=='torque_limits_nm')},
        compute_overrides=document.get('compute_parameters'),
        source_payload=document.get('source_payload'),source_ref=document.get('source_ref'))
    if result.to_dict()!=document:
        raise ContractError('configuration content differs from current catalog resolution')
    return result
