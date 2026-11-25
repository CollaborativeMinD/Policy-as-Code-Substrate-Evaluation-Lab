"""Closed scenario admission against the byte-pinned v2.0.0 analytical kernel."""
import hashlib
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent
from release_pin import RELEASE_PIN
from native_budget import LabBudget


def stamp(raw):
    return hashlib.sha256(raw).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def checked_release():
    raw = (ROOT / "release.json").read_bytes()
    check(stamp(raw) == RELEASE_PIN, "release manifest drift")
    release = json.loads(raw)
    for name, expected in release["governance"].items():
        check(stamp((ROOT / name).read_bytes()) == expected, "governance implementation drift")
    for name, expected in release["files"].items():
        check(stamp((ROOT / "_v2/Resources" / name).read_bytes()) == expected, "kernel or catalog drift")
    return release


def fields(value, required, optional=()):
    check(type(value) is dict and set(required) <= value.keys() <= set(required) | set(optional),
          "unknown or missing fields")


def component(table, catalog):
    fields(table, ("id", "parameters", "overrides"))
    check(type(table["id"]) is str and table["id"] in catalog, "unknown canonical substrate")
    profile = catalog[table["id"]]
    defaults = {f["name"]: f["default"] for f in profile["parameters"]}
    fields(table["parameters"], defaults)
    chosen = table["overrides"]
    check(type(chosen) is list and all(type(k) is str and k in defaults for k in chosen)
          and len(chosen) == len(set(chosen)), "invalid override declaration")
    for key in defaults.keys() - set(chosen):
        check(canonical(table["parameters"][key]) == canonical(defaults[key]), "unbound parameter change: " + key)
    return {key: table["parameters"][key] for key in chosen}


def wound(table):
    fields(table, ("id", "target", "severity", "onset_s", "rise_s", "end_s", "recovery_s"))
    return table | {"end_s": None if table["end_s"] == "open" else table["end_s"]}


def resolve(raw):
    check(len(raw) <= LabBudget.current().policy_bytes, "policy too large")
    release = checked_release()
    from _v2.Resources import catalog, compose, evaluate, example
    policy = tomllib.loads(raw.decode("utf-8"))
    fields(policy, ("version","name","generation","inputs","time_s","substrate","observations","wounds"),
           ("compute","source"))
    check(type(policy["version"]) is int and policy["version"] == 1, "unsupported contract")
    check(type(policy["name"]) is str and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", policy["name"]), "invalid name")
    check(type(policy["generation"]) is int and 0 < policy["generation"] < 2**63, "invalid generation")
    check(policy["inputs"] in ("teaching-fixture","operator-supplied"), "unknown input provenance")
    profiles = {p["id"]: p for p in catalog()}
    sub = policy["substrate"]
    args = {"substrate": sub["id"], "overrides": component(sub, profiles)}
    check(type(policy["wounds"]) is list and len(policy["wounds"]) <= 14, "invalid wound list")
    args["wounds"] = [wound(row) for row in policy["wounds"]]
    if "compute" in policy:
        board = policy["compute"]
        args.update(compute_overrides=component(board, profiles), compute=board["id"])
    if "source" in policy:
        fields(policy["source"], ("reference","payload"))
        args.update(source_ref=policy["source"]["reference"], source_payload=policy["source"]["payload"])
    config = compose(**args)
    observations = policy["observations"]
    if policy["inputs"] == "teaching-fixture":
        check(canonical(observations) == canonical(example(config)), "teaching observation drift")
    # These release entries have a single qualified, unmodified classroom case.
    if sub["id"] in release["reference_only"]:
        check(not args["overrides"] and not args["wounds"] and "compute" not in policy
              and policy["inputs"] == "teaching-fixture" and policy["time_s"] == 0, "outside reference scope")
    result = evaluate(config, observations, time_s=policy["time_s"])
    return policy, {"origin_sha256": release["origin"], "release_sha256": RELEASE_PIN,
                    "policy_sha256": stamp(raw), "policy_name": policy["name"], "generation": policy["generation"],
                    "input_provenance": policy["inputs"], "configuration": config.to_dict(), "effect": result}
