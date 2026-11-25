"""MCP client used by the terminal. Credentials are sent only to IPv4 loopback."""
import asyncio
from pathlib import Path
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


class Remote:
    def __init__(self, port: int, token_file: Path):
        if not 0 < port < 65536:
            raise ValueError("Invalid port")
        self.url = f"http://127.0.0.1:{port}/mcp"
        self.token_file = token_file

    async def call(self, tool_name, **arguments):
        token = self.token_file.read_text().strip()
        async with asyncio.timeout(25), httpx2.AsyncClient(
            headers={"Authorization": "Bearer " + token}, trust_env=False, follow_redirects=False
        ) as http:
            async with Client(streamable_http_client(self.url, http_client=http), mode="2026-07-28") as peer:
                reply = await peer.call_tool(tool_name, arguments)
        if reply.is_error:
            raise ValueError(" ".join(item.text for item in reply.content if hasattr(item, "text")))
        return dict(reply.structured_content)
