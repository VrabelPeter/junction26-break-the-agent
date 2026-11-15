#!/bin/bash
# Reference run: uses only the tools the agent has (the MCP server).
python3 - <<'PY'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://env-server:8000/mcp") as c:
        for _ in range(5):
            r = await c.call_tool("press", {})
            print(r.content[0].text)

asyncio.run(main())
PY
