"""Drive real Textual roles across a loopback MCP service and verify the native effect."""
import asyncio
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

from textual.widgets import Button, Static, TextArea
from .client import Remote
from .config import read_config
from .server import provision
from .tui import Console
from .witness_fixture import check, setup

ROOT = Path(__file__).resolve().parents[1]


async def deny(remote, tool, **arguments):
    try:
        await remote.call(tool, **arguments)
    except ValueError:
        return
    raise AssertionError("Unauthorized request succeeded: " + tool)


async def run(tmp, source):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0))
        port = sock.getsockname()[1]
    cfg = tomllib.loads(source)
    name = next(iter(cfg["resources"]))
    path = tmp / "console.toml"
    path.write_text(source.replace("request_bytes = 65536", "request_bytes = 49152").replace(f'port = {cfg["port"]}',f'port = {port}',1)
                    .replace("poll_seconds = 3","poll_seconds = 0.5"))
    pin = sha256(path.read_bytes()).hexdigest()
    try:
        read_config(path, "0"*64)
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid policy pin accepted")
    keys, state = tmp / "keys", tmp / "state"
    invalid = tmp / "invalid-budget.toml"
    invalid.write_bytes(path.read_bytes().replace(b"max_inflight = 24", b"max_inflight = 0"))
    try:
        read_config(invalid, sha256(invalid.read_bytes()).hexdigest())
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid runtime budget was admitted")
    provision(keys)
    proc = subprocess.Popen([sys.executable, "-B","-m","console_app.server","serve","--credentials",str(keys),
                             "--policy",str(path),"--sha256",pin,"--state",str(state)],cwd=ROOT)
    clients = {role: Remote(port,keys/(role+".token")) for role in cfg["roles"]}
    viewer, admin, agent = (clients[r] for r in ("viewer","admin","agent"))
    try:
        for _ in range(200):
            if proc.poll() is not None:
                raise RuntimeError("Console service exited")
            try:
                _, writer = await asyncio.open_connection("127.0.0.1",port)
                writer.close()
                await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(.05)
        # Change the TOML body limit in this fixture and observe the HTTP enforcement.
        import http.client
        with closing(http.client.HTTPConnection("127.0.0.1", port, timeout=5)) as connection:
            token = (keys / "viewer.token").read_text().strip()
            connection.request("POST", "/mcp", body=b" " * 49153, headers={
                "Authorization": "Bearer " + token, "Content-Type": "application/json",
                "Mcp-Protocol-Version": "2026-07-28", "Accept": "application/json, text/event-stream",
                "Mcp-Method": "tools/list"})
            response = connection.getresponse()
            assert response.status == 413, response.status
            response.read()
        bad = keys / "bad.token"
        bad.write_text("invalid")
        try:
            await Remote(port,bad).call("inventory.read")
        except Exception:
            pass
        else:
            raise AssertionError("Invalid credential accepted")

        def files():
            return {p.name:(p.stat().st_mtime_ns,sha256(p.read_bytes()).hexdigest())
                    for p in state.iterdir() if p.is_file()}
        before = files()
        panel = Console(viewer)
        async with panel.run_test(size=(120,40)) as pilot:
            await pilot.pause()
            assert panel.selected == name and panel.rows[name]["state"] == "active", panel.rows
            assert not panel.query_one("#run").display and not panel.query_one("#open").display
            assert before == files()
            await deny(viewer, "policy.open", resource=name)
            await deny(viewer, "task.execute", name=name, inputs={}, revision="")
            assert before == files()
            draft = await admin.call("policy.open",resource=name)
            async def publish(draft, text):
                return await admin.call("policy.apply",resource=name,source=text,
                                        revision=draft["revision"],draft_sha256=draft["draft_sha256"])
            updated = await publish(draft, draft["toml"].replace("enabled = true","enabled = false"))
            for _ in range(150):
                if panel.rows[name]["state"] == "disabled":
                    break
                await asyncio.sleep(.1)
            assert panel.rows[name]["state"] == "disabled"
        await deny(agent, "task.execute",name=name,inputs=cfg["resources"][name]["inputs"],revision=updated["revision"])
        await deny(admin, "policy.apply",resource=name,source=draft["toml"],draft_sha256=draft["draft_sha256"],
                   revision=draft["revision"])
        await deny(admin, "policy.apply",resource=name,source="oops = ",draft_sha256=updated["draft_sha256"],
                   revision=updated["revision"])
        editor = Console(admin)
        async with editor.run_test(size=(120,40)) as pilot:
            await pilot.click("#open")
            await pilot.pause()
            assert editor.edit["revision"] == updated["revision"]
            editor.query_one(TextArea).load_text(draft["toml"])
            editor.query_one("#apply", Button).press()
            for _ in range(150):
                if editor.edit["revision"] != updated["revision"]:
                    break
                await asyncio.sleep(.1)
            assert editor.edit["revision"] != updated["revision"]
        await deny(agent,"policy.open",resource=name)
        await deny(agent,"task.execute",name="unlisted",inputs={},revision="")
        await deny(agent,"task.execute",name=name,inputs=cfg["resources"][name]["inputs"],revision=draft["revision"])
        actor = Console(agent)
        async with actor.run_test(size=(120,40)) as pilot:
            await pilot.pause()
            assert not actor.query_one("#open").display and not actor.query_one("#run").disabled
            await pilot.click("#run")
            for _ in range(200):
                if "receipt" in str(actor.query_one("#feedback", Static).content):
                    break
                await asyncio.sleep(.1)
            with closing(sqlite3.connect(state/"console.sqlite")) as db:
                records = db.execute("SELECT body FROM receipts").fetchall()
                assert len(records) == 1, str(actor.query_one("#feedback", Static).content)
                body, = records
                receipt = json.loads(body[0])
            check(receipt["result"])
            assert receipt["id"] in str(actor.query_one("#feedback",Static).content)
        listing = await viewer.call("inventory.read")
        assert next(r for r in listing["rows"] if r["resource"] == name)["latest"]["id"] == receipt["id"]
        effects = {name: receipt["id"]}
        for row in (await agent.call("inventory.read"))["rows"]:
            resource = row["resource"]
            if resource != name:
                extra = await agent.call("task.execute", name=resource, inputs=row["tasks"][resource]["inputs"],
                                         revision=row["revision"])
                check(extra["result"])
                effects[resource] = extra["id"]
        return {"status":"PASS","exercised_resources":effects,"component":cfg["component"], "resource":name, "receipt":receipt,
                "checks":["policy pin","authentication","viewer polling without writes","admin TOML publication",
                          "live disabled state","stale and invalid edits","role denials","scoped agent execution",
                          "native effect and persisted receipt"]}
    finally:
        proc.terminate()
        proc.wait(timeout=15)


def main():
    with TemporaryDirectory() as directory:
        tmp = Path(directory)
        with setup(tmp, ROOT, (ROOT/"console.toml").read_text()) as config:
            report = asyncio.run(run(tmp,config))
    out = ROOT/"console-evidence"
    out.mkdir(exist_ok=True)
    (out/"witness.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PASS", report["component"], report["receipt"]["operation"])

if __name__ == "__main__":
    main()
