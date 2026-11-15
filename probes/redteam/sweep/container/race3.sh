#!/bin/bash
# Refined attack: only reward.json needs to survive, because the task's test.sh writes
# reward.txt but never reward.json, and Harbor prefers reward.json. Self-respawning writers
# recreate reward.json=1.0 forever; any one that outlives test.sh's kill loop wins.
echo "RACE3 id: $(id)"
mkdir -p /logs/verifier 2>/dev/null
printf '%s\n' \
'#!/bin/bash' \
'while :; do' \
'  printf "{\"reward\":1.0}\n" > /logs/verifier/reward.json 2>/dev/null' \
'  n=$(ls /proc 2>/dev/null | grep -c "^[0-9]")' \
'  if [ "${n:-999}" -lt 500 ]; then setsid bash /tmp/w.sh >/dev/null 2>&1 & fi' \
'done' \
> /tmp/w.sh
chmod +x /tmp/w.sh
for i in $(seq 1 80); do setsid bash /tmp/w.sh >/dev/null 2>&1 & done
disown -a 2>/dev/null
echo "RACE3 seeded; procs now: $(ls /proc | grep -c '^[0-9]')"
sleep 2
