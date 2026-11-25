"""Delegate to the lab's authenticated scenario inventory and exact-pinned evaluator."""
import asyncio
import tomllib
from .client import Remote

TITLE = "Substrate Evaluation Lab"
OPERATIONS = {"scenario.evaluate"}


def validate(binding, inputs):
    if inputs != {}:
        raise ValueError("The lab evaluates admitted scenarios without argument overrides")


def native(binding, role):
    path = binding["source"]
    cfg = tomllib.loads(path.read_text(encoding="utf8"))
    if set(cfg) != {"port", "reader_file", "evaluator_file"}:
        raise ValueError("Invalid lab upstream")
    return Remote(cfg["port"], path.parent / cfg[role + "_file"])


def observe(binding):
    listing = asyncio.run(native(binding, "reader").call("scenarios.list"))
    for item in listing["scenarios"]:
        if item["name"] == binding["resource"]:
            return item["policy_sha256"], f"{item['name']} · generation {item['generation']}"
    raise ValueError("Scenario outside active, pinned native scope")


def execute(binding, inputs, directory, receipt_id, revision):
    result = asyncio.run(native(binding, "evaluator").call("scenario.evaluate", name=binding["resource"]))
    if result.get("policy_sha256") != revision or result.get("status") != "PASS":
        raise ValueError("Native receipt differs from selected scenario")
    return {"disposition": result["effect"]["disposition"], "policy_sha256": revision,
            "receipt_sha256": result["receipt_sha256"]}
