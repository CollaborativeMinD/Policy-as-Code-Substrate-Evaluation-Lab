"""Run the local, role-scoped, stateless MCP server."""
import argparse
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from hmac import compare_digest
import os
from pathlib import Path
import re
import secrets
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Mount
import uvicorn

from .config import TOOLS, read_config
from .service import Service


def provision(directory):
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    for role in TOOLS:
        fd = os.open(directory / (role + ".token"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(48))


def credentials(directory):
    tokens = {}
    for role in TOOLS:
        token = (directory / (role + ".token")).read_bytes().strip()
        if not re.fullmatch(rb"[A-Za-z0-9_-]{43,128}", token):
            raise ValueError("Invalid credential")
        tokens[role] = b"Bearer " + token
    if len(set(tokens.values())) != len(tokens):
        raise ValueError("Duplicate credentials")
    return tokens


async def invoke(function, *args):
    try:
        return await asyncio.to_thread(function, *args)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    except KeyError as exc:
        raise ToolError("Unknown resource or policy field") from exc


def surface(role, service):
    grants = service.config["roles"][role]
    server = MCPServer("Component Console", version="1.1.0")

    @server.tool(name="inventory.read")
    async def inventory() -> dict[str, Any]:
        """Read component admission, running tasks and authorized controls."""
        return await invoke(service.inventory, role)

    if "policy.open" in grants:
        @server.tool(name="policy.open")
        async def open_policy(resource: str) -> dict[str, Any]:
            """Open the selected resource draft and its edit preconditions."""
            return await invoke(service.open_policy, resource)

    if "policy.apply" in grants:
        @server.tool(name="policy.apply")
        async def apply(resource: str, source: str, draft_sha256: str, revision: str) -> dict[str, Any]:
            """Admit and publish an edited task policy."""
            return await invoke(service.apply, resource, source, draft_sha256, revision)

    if "task.execute" in grants:
        @server.tool(name="task.execute")
        async def execute(name: str, inputs: dict[str, Any], revision: str) -> dict[str, Any]:
            """Run an admitted named task and return the recorded effect receipt."""
            return await invoke(service.execute, name, inputs, revision)
    return server.streamable_http_app(stateless_http=True, json_response=True, max_request_body_size=service.config["runtime"].request_bytes)


def application(config, directory, state):
    credentials(directory)
    service = Service(config, state)
    apps = {role: surface(role, service) for role in TOOLS}

    @asynccontextmanager
    async def lifespan(_):
        async with AsyncExitStack() as stack:
            for app in apps.values():
                await stack.enter_async_context(app.router.lifespan_context(app))
            yield

    async def dispatch(scope, receive, send):
        def values(key):
            return [v for k, v in scope["headers"] if k.lower() == key]

        authority = f'127.0.0.1:{config["port"]}'.encode()
        if values(b"host") != [authority] or values(b"origin") not in ([], [b"http://" + authority]):
            return await Response(status_code=403)(scope, receive, send)
        if scope["path"] != "/mcp" or scope["method"] != "POST":
            return await Response(status_code=405)(scope, receive, send)
        try:
            supplied = values(b"authorization")
            role = next((r for r, token in credentials(directory).items()
                         if len(supplied) == 1 and compare_digest(supplied[0], token)), None)
        except (ValueError, OSError):
            role = None
        if role is None:
            return await Response(status_code=401)(scope, receive, send)
        if values(b"mcp-protocol-version") != [config["protocol"].encode()]:
            return await Response(status_code=400)(scope, receive, send)
        await apps[role](scope, receive, send)

    return Starlette(routes=[Mount("/", app=dispatch)], lifespan=lifespan)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("credentials")
    init.add_argument("directory", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--credentials", required=True, type=Path)
    serve.add_argument("--state", required=True, type=Path)
    serve.add_argument("--policy", type=Path, default=Path("console.toml"))
    serve.add_argument("--sha256", required=True)
    args = parser.parse_args()
    if args.action == "credentials":
        provision(args.directory)
        return
    config = read_config(args.policy, args.sha256)
    uvicorn.run(application(config, args.credentials, args.state), host=config["host"], port=config["port"],
                access_log=False, limit_concurrency=config["runtime"].max_inflight, ws="none", proxy_headers=False)

if __name__ == "__main__":
    main()
