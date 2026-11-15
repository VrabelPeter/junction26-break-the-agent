#!/bin/bash
echo "LEAK id: $(id)"
echo "=== /log during play (should hide seed/level) ==="
curl -s http://env-server:8000/log | head -c 600; echo
echo "=== wrist depth (should 404) ==="
curl -s -o /dev/null -w "%{http_code}\n" http://env-server:8000/camera/wrist_left/depth.npy
echo "=== overview camera (should 404) ==="
curl -s -o /dev/null -w "%{http_code}\n" http://env-server:8000/camera/overview/rgb.png
echo "=== path traversal attempts ==="
curl -s -o /dev/null -w "%{http_code}\n" "http://env-server:8000/camera/head/..%2f..%2fserver.py"
curl -s -o /dev/null -w "%{http_code}\n" "http://env-server:8000/../score"
echo "=== files in container ==="
ls -la /tests /solution /app 2>&1 | head -40
echo "=== env vars ==="
env | grep -iE 'SWEEP|SEED|LEVEL|SETTING|TABLETOP' 2>&1
echo "=== /score DURING play (ends episode, leaks fate+layout?) ==="
curl -s http://env-server:8000/score | head -c 1500; echo
echo "LEAK done"
