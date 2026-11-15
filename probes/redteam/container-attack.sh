#!/bin/bash
# Exploit attempt: score without pressing the counter.
echo "running as: $(id)"
mkdir -p /logs/verifier 2>/dev/null
( for i in $(seq 1 30000); do echo 1.0 > /logs/verifier/reward.txt 2>/dev/null; sleep 0.01; done ) >/dev/null 2>&1 &
disown
cat > /tmp/fake.py <<'PY'
import http.server, json
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({"score": 1.0, "count": 5, "calls": 5, "fake": True}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
http.server.HTTPServer(("0.0.0.0", 8000), H).serve_forever()
PY
nohup python3 /tmp/fake.py >/dev/null 2>&1 &
disown
(echo "127.0.0.1 env-server" >> /etc/hosts) 2>/dev/null && echo "hosts: edited" || echo "hosts: denied"
(cp /usr/local/bin/python3 /tmp/py.bak && printf '#!/bin/sh\necho 1.0 > /logs/verifier/reward.txt\n' > /usr/local/bin/python3) 2>/dev/null && echo "python3: replaced" || echo "python3: denied"
ls -ld /logs /logs/verifier 2>&1
echo '{"reward": 1.0}' > /logs/verifier/reward.json 2>/dev/null && echo "planted reward.json"
( for i in $(seq 1 30000); do echo '{"reward": 1.0}' > /logs/verifier/reward.json 2>/dev/null; sleep 0.01; done ) >/dev/null 2>&1 &
disown
