"""Service resource budgets admitted from the operator's TOML."""
from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    request_bytes: int = Field(ge=1024, le=131072)
    max_inflight: int = Field(ge=2, le=128)
    connect_seconds: int = Field(ge=1, le=60)
    read_seconds: int = Field(ge=1, le=600)
    execute_seconds: int = Field(ge=1, le=600)
    ledger_wait_seconds: int = Field(ge=1, le=120)
    draft_bytes: int = Field(ge=128, le=65536)

    @model_validator(mode="after")
    def check_deadlines(self):
        if self.connect_seconds > min(self.read_seconds, self.execute_seconds):
            raise ValueError("Connection timeout exceeds request deadline")
        return self

    @classmethod
    def read(cls, document):
        version = document.get("version")
        if type(version) is int and version == 1 and "runtime" not in document:
            document = tomllib.loads((Path(__file__).resolve().parents[1] / "console.toml").read_text(encoding="utf8"))
        if type(document.get("version")) is not int or document["version"] != 2:
            raise ValueError("Unsupported console policy version")
        return cls.model_validate(document.get("runtime"))

    def deadline(self, operation):
        return self.execute_seconds if operation == "task.execute" else self.read_seconds
