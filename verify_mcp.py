"""Workstation wire witness. Use a temporary ledger, disposable credentials and a real child process."""
import asyncio
from contextlib import asynccontextmanager, closing
from importlib.metadata import version
import json
from pathlib import Path
import platform
import secrets
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from admission import ROOT, canonical, stamp


def cli(*args):
    return json.loads(subprocess.check_output([sys.executable, "-B", ROOT/"lab.py", *args]))


@asynccontextmanager
async def client(url, token):
    async with httpx2.AsyncClient(headers={"Authorization":"Bearer "+token}, trust_env=False) as session:
        async with Client(streamable_http_client(url, http_client=session), mode="2026-07-28") as peer:
            yield peer


def ledger_count(db):
    with closing(sqlite3.connect(db)) as conn:
        return conn.execute("SELECT count(*) FROM receipts").fetchone()[0]


async def exercise(url, tokens, db, files):
    results = {}
    expected = json.loads((ROOT/"evidence/reconciliation.json").read_bytes())["scenarios"]
    async with client(url, tokens["reader"]) as reader:
        assert [tool.name for tool in (await reader.list_tools()).tools] == ["scenarios.list"]
        denied = await reader.call_tool("scenario.evaluate", {"name":"pi-thermal"})
        assert denied.is_error and ledger_count(db) == 0
    async with client(url, tokens["evaluator"]) as peer:
        assert peer.protocol_version == "2026-07-28"
        names = (await peer.call_tool("scenarios.list", {})).structured_content["scenarios"]
        assert {item["name"] for item in names} == set(expected)
        for name in sorted(expected):
            call = await peer.call_tool("scenario.evaluate", {"name":name})
            body = dict(call.structured_content)
            digest = body.pop("receipt_sha256")
            assert body.pop("status") == "PASS"
            assert stamp(canonical(body)) == digest == expected[name]["receipt_sha256"]
            assert stamp(canonical(body["effect"])) == expected[name]["effect_sha256"]
            results[name] = {"receipt_sha256":digest, "disposition":body["effect"]["disposition"]}
        count = ledger_count(db)
        assert count == len(files)
        assert (await peer.call_tool("scenario.evaluate", {"name":"../private"})).is_error
        assert (await peer.call_tool("scenario.evaluate", {"name":"pi-thermal"})).structured_content["receipt_sha256"] == results["pi-thermal"]["receipt_sha256"]
        updated = db.parent/"replacement.toml"
        updated.write_bytes((ROOT/"policies/pi-thermal.toml").read_bytes().replace(b"generation = 1", b"generation = 2"))
        cli("admit",updated,"--state",db,"--sha256",stamp(updated.read_bytes()))
        assert (await peer.call_tool("scenario.evaluate", {"name":"pi-thermal"})).is_error
        listing = (await peer.call_tool("scenarios.list", {})).structured_content["scenarios"]
        assert "pi-thermal" not in {row["name"] for row in listing}
        assert ledger_count(db) == count
    return results


async def verify(tmp):
    db = tmp/"state.sqlite"
    files = sorted((ROOT/"policies").glob("*.toml"))
    for path in files:
        cli("admit",path,"--state",db,"--sha256",stamp(path.read_bytes()))
    tokens = {r:secrets.token_urlsafe(32) for r in ("reader","evaluator")}
    for role, token in tokens.items():
        (tmp/(role+".token")).write_text(token)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    original = (ROOT/"mcp-policy.toml").read_bytes()
    policy = tmp/"transport.toml"
    policy.write_bytes(original.replace(b"port = 8765",f"port = {port}".encode()))
    url = f"http://127.0.0.1:{port}/mcp"
    args = [sys.executable,"-B",ROOT/"lab_mcp.py","--policy",policy,"--credentials",tmp,"--state",db,"--sha256"]
    bad = subprocess.run([*args,"0"*64],capture_output=True,timeout=15)
    assert bad.returncode != 0 and b"MCP policy pin mismatch" in bad.stderr
    process = subprocess.Popen([*args,stamp(policy.read_bytes())],stdout=subprocess.DEVNULL)
    try:
        async with httpx2.AsyncClient(trust_env=False) as http:
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError("MCP server exited before readiness")
                try:
                    response = await http.post(url,json={})
                    break
                except httpx2.ConnectError:
                    await asyncio.sleep(.05)
            else:
                raise RuntimeError("MCP readiness timed out")
            assert response.status_code == 401
            assert (await http.post(url,headers={"Origin":"https://invalid.example"})).status_code == 403
        results = await exercise(url,tokens,db,files)
    finally:
        process.terminate()
        process.wait(timeout=15)
    config = tomllib.loads(original.decode())
    assert {p.stem:stamp(p.read_bytes()) for p in files} == config["scenarios"]
    return {"status":"PASS","protocol":config["protocol"],"mcp_sdk":version("mcp"),"python":platform.python_version(),
            "platform":platform.system(),"transport_policy_sha256":stamp(original),
            "server_sha256":stamp((ROOT/"lab_mcp.py").read_bytes()), "test_port":"ephemeral IPv4 loopback",
            "checks":["incorrect transport pin rejected","unauthenticated request rejected","foreign origin rejected",
                      "reader cannot evaluate","all admitted effects match v2 reconciliation","unlisted name rejected",
                      "repeat is idempotent","superseded policy hidden and denied","denials create no receipts"],
            "scenarios":results}


if __name__ == "__main__":
    with TemporaryDirectory() as folder:
        report = asyncio.run(verify(Path(folder)))
    (ROOT/"evidence/mcp-workstation.json").write_bytes(json.dumps(report,indent=2,sort_keys=True).encode()+b"\n")
    print("PASS:", len(report["scenarios"]), "effects and receipts verified")
