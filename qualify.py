"""Replay baseline and governed paths in separate subprocesses, then reconcile records."""
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from admission import ROOT, canonical, checked_release, stamp


def run(cwd, args, expected=0):
    result = subprocess.run([sys.executable, "-B", *map(str,args)], cwd=cwd, capture_output=True, timeout=240)
    if result.returncode != expected:
        raise RuntimeError(result.stderr.decode(errors="replace")[-3000:])
    return json.loads((result.stdout if expected == 0 else result.stderr).decode())


def candidate(path, db, action, expected=0, pin=None):
    args = [ROOT/"lab.py", action, path, "--state", db]
    if action == "admit":
        args += ["--sha256", pin if pin is not None else stamp(path.read_bytes())]
    return run(ROOT, args, expected)


def negatives(tmp, db):
    sample = ROOT/"policies/pi-thermal.toml"
    source = sample.read_text()
    staged = tmp/"candidate.toml"
    failures = {}
    cases = {
        "unknown_key": source.replace("version = 1","version = 1\nextra = true"),
        "missing_observation": source.replace("temperature_c = 45",""),
        "unknown_unit": source.replace("temperature_c = 45",'temperature_c = { value=45, unit="incorrect" }')
                              .replace("teaching-fixture","operator-supplied"),
        "unbound_parameter": source.replace("alternate_c = 70","alternate_c = 71"),
        "boolean_as_number": source.replace("severity = 1.0","severity = true"),
        "duplicate_toml": source.replace("version = 1","version = 1\nversion = 1"),
        "unbound_substrate": source.replace("controller.raspberry_pi5_8gb.v1","unregistered"),
    }
    for name, raw in cases.items():
        staged.write_text(raw)
        failures[name] = candidate(staged, db, "admit", 2)["reason"]
    scoped = next((ROOT/"policies").glob("radar-xband-*.toml"))
    staged.write_text(scoped.read_text().replace("time_s = 0","time_s = 1"))
    failures["outside_reference_scope"] = candidate(staged, db, "admit", 2)["reason"]
    failures["wrong_pin"] = candidate(sample, db, "admit", 2, "0"*64)["reason"]
    staged.write_text(source.replace("severity = 1.0","severity = 0.5"))
    failures["unapproved_bytes"] = candidate(staged, db, "run", 2)["reason"]
    failures["generation_collision"] = candidate(staged, db, "admit", 2)["reason"]
    staged.write_text(staged.read_text().replace("generation = 1","generation = 2"))
    candidate(staged, db, "admit")
    updated = candidate(staged, db, "run")
    assert updated["effect"]["effective_inputs"]["temperature_c"] == 65
    failures["stale_after_activation"] = candidate(sample, db, "run", 2)["reason"]
    failures["rollback"] = candidate(sample, db, "admit", 2)["reason"]
    return failures


def compare(tmp, db, answers):
    rows = {}
    for name, (config, effect) in answers.items():
        policy = ROOT/"policies"/(name+".toml")
        candidate(policy, db, "admit")
        receipt = candidate(policy, db, "run")
        assert canonical(receipt["configuration"]) == canonical(config), name
        assert canonical(receipt["effect"]) == canonical(effect), name
        digest = receipt.pop("receipt_sha256")
        receipt.pop("status")
        assert stamp(canonical(receipt)) == digest
        with closing(sqlite3.connect(db)) as connection:
            stored, = connection.execute("SELECT body FROM receipts WHERE digest=?", (digest,)).fetchone()
            assert stored == canonical(receipt)
            source, = connection.execute("SELECT document FROM admissions WHERE digest=?",
                                        (receipt["policy_sha256"],)).fetchone()
            assert source == policy.read_bytes()
        rows[name] = {"disposition":effect["disposition"],"receipt_sha256":digest,
                      "effect_sha256":stamp(canonical(effect)), "v2_config_sha256":effect["config_hash"]}
    assert len(rows) == len(list((ROOT/"policies").glob("*.toml")))
    return rows


def main():
    archive = ROOT/"reference/HMT_Substrate_Lab_v2.0.0.zip"
    assert stamp(archive.read_bytes()) == checked_release()["origin"]
    with TemporaryDirectory() as folder:
        tmp = Path(folder)
        with ZipFile(archive) as original:
            original.extractall(tmp)
        baseline = tmp/"Substrate_Lab"
        evidence = baseline/"Resources/evidence/verification.json"
        historical = json.loads(evidence.read_bytes())
        gates = run(baseline, ["-m","Resources.verify","--references"])
        replay = json.loads(evidence.read_bytes())
        shutil.copyfile(ROOT/"reference/oracle.py",baseline/"oracle.py")
        answers = run(baseline, ["oracle.py"])
        db = tmp/"ledger.sqlite"
        rows = compare(tmp, db, answers)
        before = sqlite3.connect(db)
        initial = before.execute("SELECT count(*) FROM receipts").fetchone()[0]
        failures = negatives(tmp, db)
        assert before.execute("SELECT count(*) FROM receipts").fetchone()[0] == initial+1
        before.close()
    keys = lambda data: sorted((r["gate"],r["subject"],r["status"]) for r in data)
    if keys(historical) != keys(replay):
        print("Gate differences", set(keys(historical)) ^ set(keys(replay)))
        raise ValueError("archived gate dispositions differ")
    report = {"status":"PASS","origin_sha256":stamp(archive.read_bytes()),"baseline_replay":gates,
              "historical_gate_dispositions_equal":True,"scenarios":rows,"denials":failures,
              "comparison":"Canonical JSON equality of complete configuration and complete effect receipt"}
    out = ROOT/"evidence/reconciliation.json"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(json.dumps(report,indent=2,sort_keys=True).encode()+b"\n")
    print("PASS", len(rows), "scenarios,", len(failures), "denials,", gates)


if __name__ == "__main__":
    main()
