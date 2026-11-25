"""MCP client used by the terminal. Credentials are sent only to IPv4 loopback."""
import asyncio
import tomllib
from .runtime_policy import RuntimePolicy
from pathlib import Path
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


class Remote:
    def __init__(self, port: int, token_file: Path, limits=None):
        if not 0 < port < 65536:
            raise ValueError("Invalid port")
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.token_file = token_file
        self.limits = limits or RuntimePolicy.read(tomllib.loads(
            (Path(__file__).resolve().parents[1] / "console.toml").read_text(encoding="utf8")))

    async def call(self, tool_name, **arguments):
        token = self.token_file.read_text().strip()
        deadline = self.limits.deadline(tool_name)
        async with asyncio.timeout(deadline), httpx2.AsyncClient(
            timeout=httpx2.Timeout(deadline, connect=self.limits.connect_seconds),
            headers={"Authorization": "Bearer " + token}, trust_env=False, follow_redirects=False
        ) as http:
            async with Client(streamable_http_client(self.url, http_client=http), mode="2026-07-28") as peer:
                reply = await peer.call_tool(tool_name, arguments)
        if reply.is_error:
            raise ValueError(" ".join(item.text for item in reply.content if hasattr(item, "text")))
        return dict(reply.structured_content)
