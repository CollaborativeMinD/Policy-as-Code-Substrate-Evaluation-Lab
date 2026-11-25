"""Admit operational budgets independently of model and wire contracts."""
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class LabBudget:
    ledger_wait_seconds: int
    policy_bytes: int

    @classmethod
    def current(cls):
        return cls.read(Path(__file__).with_name("lab_runtime.toml"))

    @classmethod
    def read(cls, path):
        with Path(path).open("rb") as stream:
            values = tomllib.load(stream)
        if set(values) != set(cls.__annotations__):
            raise ValueError("Unknown or missing runtime budget")
        if type(values["ledger_wait_seconds"]) is not int or not 1 <= values["ledger_wait_seconds"] <= 120:
            raise ValueError("Invalid ledger_wait_seconds")
        if type(values["policy_bytes"]) is not int or not 1 <= values["policy_bytes"] <= 131072:
            raise ValueError("Invalid policy_bytes")
        return cls(**values)
