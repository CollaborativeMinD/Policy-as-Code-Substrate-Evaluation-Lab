"""Admit a trusted TOML digest or evaluate the currently admitted document."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
from admission import MAX_POLICY, canonical, check, resolve, stamp


def transact(action, path, state, approved=None):
    with path.open("rb") as stream:
        raw = stream.read(MAX_POLICY + 1)
    digest = stamp(raw)
    if action == "admit":
        check(digest == approved, "candidate differs from approved digest")
    check(action in ("admit","run"), "unknown operation")
    with closing(sqlite3.connect(state if action == "admit" else state.resolve().as_uri()+"?mode=rw",
                                 uri=action=="run", timeout=10)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        if action == "admit":
            db.execute("CREATE TABLE IF NOT EXISTS active(name TEXT PRIMARY KEY, generation INTEGER, digest TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS admissions(digest TEXT PRIMARY KEY, document BLOB NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS receipts(digest TEXT PRIMARY KEY, body BLOB NOT NULL)")
        if action == "run":
            active = db.execute("SELECT document FROM admissions JOIN active USING(digest) WHERE digest=?",
                                (digest,)).fetchone()
            check(active == (raw,), "policy not active or admission record differs")
        policy, body = resolve(raw)
        name, generation = policy["name"], policy["generation"]
        if action == "admit":
            old = db.execute("SELECT generation,digest FROM active WHERE name=?", (name,)).fetchone()
            check(old is None or old == (generation,digest) or generation > old[0], "generation conflict or rollback")
            db.execute("INSERT OR IGNORE INTO admissions VALUES(?,?)", (digest, raw))
            db.execute("INSERT OR REPLACE INTO active VALUES(?,?,?)", (name,generation,digest))
            return {"status":"ADMITTED","generation":generation,"policy_sha256":digest}
        receipt = canonical(body)
        receipt_hash = stamp(receipt)
        db.execute("INSERT OR IGNORE INTO receipts VALUES(?,?)", (receipt_hash, receipt))
        stored, = db.execute("SELECT body FROM receipts WHERE digest=?", (receipt_hash,)).fetchone()
        check(stored == receipt, "receipt integrity mismatch")
        return {"status":"PASS","receipt_sha256":receipt_hash,**body}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action",required=True)
    for name in ("admit","run"):
        cmd = commands.add_parser(name)
        cmd.add_argument("policy",type=Path)
        cmd.add_argument("--state",type=Path,required=True)
        if name == "admit":
            cmd.add_argument("--sha256",required=True)
    args = parser.parse_args()
    try:
        receipt = transact(args.action,args.policy,args.state,getattr(args,"sha256",None))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,RecursionError,OverflowError) as exc:
        print(json.dumps({"status":"DENY","reason":str(exc)}),file=sys.stderr)
        return 2
    print(json.dumps(receipt,sort_keys=True,allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
