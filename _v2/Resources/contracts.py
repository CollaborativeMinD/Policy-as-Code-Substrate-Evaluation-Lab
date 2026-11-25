"""Strict numeric and immutable JSON contracts; no unit-library dependency."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from numbers import Real


class ContractError(ValueError):
    """A request is outside the declared model contract."""


def number(value, name, lower=-1e15, upper=1e15, kind='real'):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ContractError(f'{name}: expected {kind}, got {type(value).__name__}')
    value = float(value)
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ContractError(f'{name}: finite value in [{lower}, {upper}] required')
    if kind == 'integer':
        if not value.is_integer():
            raise ContractError(f'{name}: integer required')
        return int(value)
    return value


def quantity(value, field):
    if isinstance(value, dict):
        if set(value) != {'value', 'unit'} or value['unit'] != field['unit']:
            raise ContractError(f"{field['name']}: supply value and exact unit {field['unit']}")
        value = value['value']
    if field['kind'] == 'vector7':
        if not isinstance(value, (list, tuple)) or len(value) != 7:
            raise ContractError(f"{field['name']}: seven components required")
        return [number(v, field['name'], field['lower'], field['upper']) for v in value]
    return number(value, field['name'], field['lower'], field['upper'], field['kind'])


def validate(fields, values, complete=True):
    if not isinstance(values, dict):
        raise ContractError('values must be an object')
    known = {f['name']: f for f in fields}
    extra = set(values) - set(known)
    missing = set(known) - set(values) if complete else set()
    if extra or missing:
        raise ContractError(f'unknown={sorted(extra)}, missing={sorted(missing)}')
    return {k: quantity(v, known[k]) for k, v in values.items()}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


@dataclass(frozen=True)
class ResolvedConfiguration:
    """JSON is the immutable source; returned dictionaries are detached copies."""
    document: str

    @property
    def digest(self):
        return sha256(self.document.encode()).hexdigest()

    def to_dict(self):
        return json.loads(self.document)
