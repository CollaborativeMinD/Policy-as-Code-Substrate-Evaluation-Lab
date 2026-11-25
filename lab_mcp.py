"""Authenticated stateless MCP adapter for already-admitted TOML scenarios."""
import argparse
from contextlib import AsyncExitStack, asynccontextmanager, closing
from hmac import compare_digest
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import tomllib
from typing import Any

from mcp.server import MCPServer
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount
import uvicorn

from admission import MAX_POLICY, check, checked_release, fields, stamp
from lab import transact

TOOLS = {"scenarios.list", "scenario.evaluate"}


def load_policy(path, approved):
    with path.open("rb") as src:
        raw = src.read(MAX_POLICY + 1)
    check(len(raw) <= MAX_POLICY and stamp(raw) == approved, "MCP policy pin mismatch")
    policy = tomllib.loads(raw.decode())
    fields(policy, ("version", "protocol", "host", "port", "roles", "scenarios"))
    check(type(policy["version"]) is int and policy["version"] == 1, "unsupported policy")
    check(policy["protocol"] == "2026-07-28" and policy["host"] == "127.0.0.1", "unsupported transport")
    check(type(policy["port"]) is int and 0 < policy["port"] <= 65535, "invalid port")
    fields(policy["roles"], ("reader", "evaluator"))
    for grants in policy["roles"].values():
        check(type(grants) is list and set(grants) <= TOOLS and len(set(grants)) == len(grants), "invalid grants")
    check("scenario.evaluate" not in policy["roles"]["reader"], "reader cannot evaluate")
    scenarios = policy["scenarios"]
    check(type(scenarios) is dict and 0 < len(scenarios) <= 256, "invalid scope")
    for name, digest in scenarios.items():
        check(re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) and type(digest) is str
              and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid scenario pin")
    return policy


def read_state(state):
    return sqlite3.connect(state.resolve().as_uri() + "?mode=ro", uri=True)


def surface(grants, scope, state):
    server = MCPServer("Governed Substrate Lab", version="1.0.0",
                       instructions="Select an admitted TOML scenario by name. Read effect.disposition for the model result.")

    if "scenarios.list" in grants:
        @server.tool(name="scenarios.list")
        def scenarios_list() -> dict[str, Any]:
            """List active scenarios matched by this server's pinned policy."""
            with closing(read_state(state)) as db:
                rows = db.execute("SELECT name,generation,digest FROM active ORDER BY name").fetchall()
            return {"scenarios": [{"name": n, "generation": g, "policy_sha256": d}
                                  for n, g, d in rows if scope.get(n) == d]}

    if "scenario.evaluate" in grants:
        @server.tool(name="scenario.evaluate")
        def scenario_evaluate(name: str) -> dict[str, Any]:
            """Evaluate the admitted TOML and return its full governed receipt."""
            digest = scope.get(name)
            if digest is None:
                raise ValueError("SCENARIO_DENIED")
            with closing(read_state(state)) as db:
                row = db.execute("SELECT document FROM admissions JOIN active USING(digest) "
                                 "WHERE name=? AND digest=?", (name, digest)).fetchone()
            check(row is not None and stamp(row[0]) == digest, "SCENARIO_INACTIVE")
            # Supply immutable bytes to the existing file API. Its own transaction
            # checks active state again and commits the effect and receipt together.
            with TemporaryDirectory() as folder:
                candidate = Path(folder) / "admitted.toml"
                candidate.write_bytes(row[0])
                return transact("run", candidate, state)

    return server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=65536)


def credentials(directory):
    tokens = {}
    for role in ("reader", "evaluator"):
        with (directory / (role + ".token")).open("rb") as src:
            token = src.read(258).strip()
        check(re.fullmatch(rb"[A-Za-z0-9_-]{43,128}", token), "invalid host credential")
        tokens[role] = b"Bearer " + token
    check(tokens["reader"] != tokens["evaluator"], "duplicate role credentials")
    return tokens


def application(policy, state, directory):
    credentials(directory)
    apps = {role: surface(grants, policy["scenarios"], state) for role, grants in policy["roles"].items()}

    @asynccontextmanager
    async def lifespan(_):
        async with AsyncExitStack() as stack:
            for app in apps.values():
                await stack.enter_async_context(app.router.lifespan_context(app))
            yield

    async def dispatch(scope, receive, send):
        def values(key):
            return [v for k, v in scope["headers"] if k.lower() == key]

        authority = f'127.0.0.1:{policy["port"]}'.encode()
        if values(b"host") != [authority] or values(b"origin") not in ([], [b"http://" + authority]):
            return await Response(status_code=403)(scope, receive, send)
        try:
            supplied = values(b"authorization")
            role = next((r for r, t in credentials(directory).items()
                         if len(supplied) == 1 and compare_digest(supplied[0], t)), None)
        except (ValueError, OSError):
            role = None
        if role is None:
            return await Response(status_code=401, headers={"WWW-Authenticate":"Bearer"})(scope, receive, send)
        if scope["method"] != "POST" or scope["path"] != "/mcp":
            return await Response(status_code=405)(scope, receive, send)
        if values(b"mcp-protocol-version") != [policy["protocol"].encode()]:
            return await Response(status_code=400)(scope, receive, send)

        async def private(message):
            if message["type"] == "http.response.start":
                message["headers"] = [(k,v) for k,v in message["headers"] if k.lower() != b"cache-control"]
                message["headers"].append((b"cache-control", b"private, no-store"))
            await send(message)
        await apps[role](scope, receive, private)

    return Starlette(routes=[Mount("/", app=dispatch)], lifespan=lifespan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    checked_release()
    policy = load_policy(args.policy, args.sha256)
    uvicorn.run(application(policy, args.state, args.credentials), host=policy["host"], port=policy["port"],
                access_log=False, proxy_headers=False, ws="none")


if __name__ == "__main__":
    main()

