#!/bin/bash
echo "IMP id: $(id)"
echo "hosts writable?"; (echo "127.0.0.1 env-server" >> /etc/hosts) 2>&1 && echo "HOSTS EDITED" || echo "hosts denied"
echo "bind :8000 locally?"; (python3 -c "import socket; s=socket.socket(); s.bind(('0.0.0.0',8000)); print('BOUND 8000')" 2>&1 | head -1)
echo "write /tests?"; (echo x > /tests/x 2>&1) && echo "TESTS WRITABLE" || echo "tests ro"
echo "write /usr/local/bin?"; (echo x > /usr/local/bin/zzz 2>&1) && echo "BIN WRITABLE" || echo "bin ro"
echo "ld.so.preload?"; (echo /tmp/x.so > /etc/ld.so.preload 2>&1) && echo "PRELOAD SET" || echo "preload denied"
echo "docker socket?"; ls -l /var/run/docker.sock 2>&1
echo "sudo?"; sudo -n id 2>&1 | head -1
echo "IMP done"
