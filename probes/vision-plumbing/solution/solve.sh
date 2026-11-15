#!/bin/bash
# Not a real reference: the oracle cannot see either. It only exercises the tools.
python3 - <<'PY'
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://env-server:8000/mcp") as c:
        for name in ("look_image_only", "look_image_and_text"):
            r = await c.call_tool(name, {})
            print(name, [type(x).__name__ for x in r.content])
        for route in ("image_only", "image_and_text", "file"):
            await c.call_tool("answer", {"route": route, "description": "cannot see"})

asyncio.run(main())
PY
