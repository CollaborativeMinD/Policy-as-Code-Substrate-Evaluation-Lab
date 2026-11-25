"""Admit operational budgets independently of model and wire contracts."""
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class LabBudget:
    ledger_wait_seconds: int

    @classmethod
    def read(cls, path):
        with Path(path).open("rb") as stream:
            values = tomllib.load(stream)
        if set(values) != set(cls.__annotations__):
            raise ValueError("Unknown or missing runtime budget")
        if type(values["ledger_wait_seconds"]) is not int or not 1 <= values["ledger_wait_seconds"] <= 120:
            raise ValueError("Invalid ledger_wait_seconds")
        return cls(**values)
