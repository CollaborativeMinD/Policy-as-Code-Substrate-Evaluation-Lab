"""Explicit source injection and opt-in replay of hash-verified frozen references."""
from dataclasses import asdict, is_dataclass
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import importlib
import json
import sys
import tempfile
import zipfile
from .contracts import ContractError, quantity
from .registry import ROOT, select
from .reference_storage import reference_root


def panda_parameters(payload):
    if not isinstance(payload,dict) or set(payload) != {'joint_dynamics'}:
        raise ContractError('Panda injection accepts only joint_dynamics; no ignored fields')
    inner = payload['joint_dynamics']
    if not isinstance(inner,dict) or set(inner) != {'torque_limits'}:
        raise ContractError('joint_dynamics requires exactly torque_limits')
    field = select('robotic.franka_panda.v4')['parameters'][0]
    return {'torque_limits_nm':quantity(inner['torque_limits'],field)}



def reference_record(identity):
    rows = json.loads((ROOT/'evidence/legacy_registry.json').read_text())
    direct = next((r for r in rows if identity==r['substrate_id']),None)
    if direct is not None:
        return direct
    sid = select(identity)['legacy_source_id']
    return next(r for r in rows if r['substrate_id']==sid)


def load_reference(identity, *, factory_arguments=None, transfer_version="bundle"):
    """Honor the entire dotted factory. Arguments are explicit; no silent fallback."""
    _,_,namespace=reference_root(transfer_version)
    row = reference_record(identity)
    obj = importlib.import_module(row['profile_module'].replace('substrate_profiles_registry',namespace,1))
    for part in row['profile_factory'].split('.'):
        obj = getattr(obj,part)
    if '.' in row['profile_factory'] and factory_arguments is None:
        raise ContractError('source-backed factory requires explicit factory_arguments')
    return obj(**(factory_arguments or {}))


def reference_wound(identity, profile, inputs):
    """Replay historic output names and heuristic semantics without promotion."""
    row = reference_record(identity)
    namespace=type(profile).__module__.split('.')[0]
    factory = getattr(importlib.import_module(row['wound_module'].replace('substrate_profiles_registry',namespace,1)),row['wound_factory'])
    if row['substrate_id'] in ('controller.raspberry_pi5_8gb.v1','controller.jetson_orin_nano_8gb.v1'):
        result = factory(inputs)
    else:
        result = factory(profile=profile,**inputs)
    return dict(disposition='REFERENCE_REPLAY_NOT_PHYSICAL_CALIBRATION',
                transfer_version=namespace.removeprefix('hmt_substrate_'),result=serialize(result),
                note='Unreported assessment fields remain null in the recovered schema; never infer healthy state.')


def serialize(obj):
    if is_dataclass(obj):
        return serialize(asdict(obj))
    if isinstance(obj,dict):
        return {k:serialize(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):
        return [serialize(v) for v in obj]
    if hasattr(obj,'value'):
        return obj.value
    if hasattr(obj,'tolist'):
        return obj.tolist()
    return obj
