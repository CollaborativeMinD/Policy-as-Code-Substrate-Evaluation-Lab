"""Admit console task policies and retain effects in a service-owned SQLite ledger."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
import sqlite3
from threading import Lock
import tomllib
from uuid import uuid4

from . import adapter
from .config import digest


def checked_policy(source, binding):
    if len(source.encode()) > 16384:
        raise ValueError("Draft too large")
    doc = tomllib.loads(source)
    if set(doc) != {"enabled", "inputs"} or type(doc["enabled"]) is not bool:
        raise ValueError("Expected enabled and inputs")
    adapter.validate(binding, doc["inputs"])
    return doc


def starter(binding):
    return "enabled = true\n\n[inputs]\n" + "".join(
        f"{key} = {json.dumps(value, ensure_ascii=False)}\n" for key, value in binding["inputs"].items())


class Service:
    def __init__(self, config, state):
        self.config = config
        self.directory = state.resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "console.sqlite"
        self.lock = Lock()
        self.running = set()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS policy(pin TEXT, resource TEXT, generation INTEGER, source TEXT,
                    PRIMARY KEY(pin, resource));
                CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, pin TEXT, resource TEXT, body TEXT);
                CREATE INDEX IF NOT EXISTS receipt_lookup ON receipts(pin, resource);
            """)
            for name, binding in config["resources"].items():
                db.execute("INSERT OR IGNORE INTO policy VALUES (?,?,1,?)",
                           (config["pin"], name, starter(binding)))

    @contextmanager
    def connection(self, write=False):
        mode = "rw" if write else "ro"
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=" + mode, uri=True, timeout=10)) as db, db:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db

    def snapshot(self, db, name):
        binding = self.config["resources"].get(name)
        if binding is None:
            raise ValueError("Resource outside console scope")
        generation, source = db.execute("SELECT generation,source FROM policy WHERE pin=? AND resource=?",
                                        (self.config["pin"], name)).fetchone()
        doc = checked_policy(source, binding)
        version = digest(source.encode())
        revision = f"{self.config['pin']}/{generation}/{version}"
        return binding, doc, {"resource": name, "toml": source, "draft_sha256": version, "revision": revision}

    def inventory(self, role):
        rows = []
        with self.connection() as db:
            for name in self.config["resources"]:
                binding, doc, edit = self.snapshot(db, name)
                try:
                    native, detail = adapter.observe(binding)
                    state = "active" if doc["enabled"] else "disabled"
                except Exception:
                    native, detail, state = "", "Native observation unavailable", "unverified"
                receipt = db.execute("SELECT body FROM receipts WHERE pin=? AND resource=? ORDER BY rowid DESC LIMIT 1",
                                     (self.config["pin"], name)).fetchone()
                latest = None
                if receipt:
                    record = json.loads(receipt[0])
                    latest = {k: record[k] for k in ("task", "at", "id")}
                tasks = {}
                if role == "agent" and state == "active" and "task.execute" in self.config["roles"][role]:
                    tasks[name] = {"inputs": doc["inputs"]}
                with self.lock:
                    running = int(name in self.running)
                rows.append({"resource": name, "state": state, "detail": detail, "running": running, "latest": latest,
                             "revision": edit["revision"] + "/" + native, "tasks": tasks})
        return {"rows": rows, "component": self.config["component"], "role": role,
                "tools": self.config["roles"][role], "poll_seconds": self.config["poll_seconds"]}

    def open_policy(self, resource):
        with self.connection() as db:
            binding, _, edit = self.snapshot(db, resource)
            native, _ = adapter.observe(binding)
            edit["revision"] += "/" + native
            return edit

    def apply(self, resource, source, draft_sha256, revision):
        with self.connection(True) as db:
            binding, _, edit = self.snapshot(db, resource)
            native, _ = adapter.observe(binding)
            if edit["draft_sha256"] != draft_sha256 or revision != edit["revision"] + "/" + native:
                raise ValueError("Stale draft; open the current revision")
            checked_policy(source, binding)
            db.execute("UPDATE policy SET generation=generation+1,source=? WHERE pin=? AND resource=?",
                       (source, self.config["pin"], resource))
            _, _, updated = self.snapshot(db, resource)
            updated["revision"] += "/" + native
            return {"disposition": "published", **updated}

    def execute(self, name, inputs, revision):
        with self.connection(True) as db:
            binding, doc, edit = self.snapshot(db, name)
            native, _ = adapter.observe(binding)
            if not doc["enabled"] or revision != edit["revision"] + "/" + native:
                raise ValueError("Disabled task or stale revision")
            adapter.validate(binding, inputs)
            if any(inputs[key] != value for key, value in doc["inputs"].items() if key not in binding["editable_inputs"]):
                raise ValueError("Input is fixed by the admitted policy")
            receipt_id = uuid4().hex
            with self.lock:
                self.running.add(name)
            try:
                result = adapter.execute(binding, inputs, self.directory, receipt_id, native)
                receipt = {"disposition": "executed", "id": receipt_id, "task": name,
                           "at": datetime.now(timezone.utc).isoformat(), "revision": revision,
                           "operation": binding["operation"], "result": result}
                db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (receipt_id, self.config["pin"], name,
                           json.dumps(receipt, allow_nan=False)))
                return receipt
            finally:
                with self.lock:
                    self.running.discard(name)
