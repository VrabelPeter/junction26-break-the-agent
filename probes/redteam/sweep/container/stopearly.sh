#!/bin/bash
echo "STOPEARLY id: $(id)"
# touch the MCP server a little then quit: curl observe, then stop.
curl -s http://env-server:8000/log || true
echo "STOPEARLY done"
