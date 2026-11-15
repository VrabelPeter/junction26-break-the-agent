#!/bin/bash
# Reference run: a scripted controller that uses only the MCP tools the agent has.
cd "$(dirname "$0")"
# SHAPES_POLICY=stop_early runs the stop-early baseline (seats the first peg, then walks away).
python3 - "${SHAPES_POLICY:-${TABLETOP_POLICY:-reference}}" <<'PY'
import asyncio, json, sys
from fastmcp import Client
import policies

async def main(name):
    async with Client("http://env-server:8000/mcp") as c:
        loop = asyncio.get_running_loop()
        def call(tool, **args):
            fut = asyncio.run_coroutine_threadsafe(c.call_tool(tool, args), loop)
            return json.loads(fut.result().content[0].text)
        task = json.loads((await c.call_tool("get_task", {})).content[0].text)
        await asyncio.to_thread(policies.POLICIES[name], call, task)
        print("done", name)

asyncio.run(main(sys.argv[1]))
PY
