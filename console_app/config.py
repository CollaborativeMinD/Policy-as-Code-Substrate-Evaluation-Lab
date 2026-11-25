"""The approved host policy selects a subset of reviewed component operations."""
from hashlib import sha256
from pathlib import Path
import re
import tomllib

from .runtime_policy import RuntimePolicy

from . import adapter

TOOLS = {"viewer": {"inventory.read"}, "admin": {"inventory.read", "policy.open", "policy.apply"},
         "agent": {"inventory.read", "task.execute"}}


def digest(raw):
    return sha256(raw).hexdigest()


def read_config(path, pin):
    raw = path.read_bytes()
    if len(raw) > 65536 or digest(raw) != pin:
        raise ValueError("Console policy digest mismatch")
    cfg = tomllib.loads(raw.decode())
    limits = RuntimePolicy.read(cfg)
    if ((set(cfg) - {"runtime"}) != {"version", "component", "host", "port", "protocol", "poll_seconds", "roles", "resources"}
            or type(cfg["version"]) is not int or cfg["version"] not in (1, 2) or cfg["component"] != adapter.TITLE
            or cfg["host"] != "127.0.0.1" or cfg["protocol"] != "2026-07-28"
            or type(cfg["port"]) is not int or not 0 < cfg["port"] < 65536
            or type(cfg["poll_seconds"]) not in (int, float) or not .25 <= cfg["poll_seconds"] <= 300
            or set(cfg["roles"]) != set(TOOLS) or not isinstance(cfg["resources"], dict)):
        raise ValueError("Invalid transport, component or role declaration")
    for role, grants in cfg["roles"].items():
        if (not isinstance(grants, list) or not set(grants) <= TOOLS[role]
                or len(set(grants)) != len(grants) or "inventory.read" not in grants):
            raise ValueError("Invalid grant")
    if "policy.apply" in cfg["roles"]["admin"] and "policy.open" not in cfg["roles"]["admin"]:
        raise ValueError("Publication requires draft access")
    for name, binding in cfg["resources"].items():
        if (not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name)
                or set(binding) != {"operation", "source", "inputs", "editable_inputs"} or binding["operation"] not in adapter.OPERATIONS
                or type(binding["source"]) is not str or not binding["source"]):
            raise ValueError("Unknown resource binding")
        binding["source"] = (path.resolve().parent / binding["source"]).resolve()
        editable = binding["editable_inputs"]
        if not isinstance(editable, list) or not set(editable) <= binding["inputs"].keys() or len(set(editable)) != len(editable):
            raise ValueError("Unknown or duplicate editable task input")
        binding["resource"] = name
        adapter.validate(binding, binding["inputs"])
    cfg["pin"] = pin
    cfg["runtime"] = limits
    return cfg
