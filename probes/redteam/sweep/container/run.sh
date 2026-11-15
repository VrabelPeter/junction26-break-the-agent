#!/bin/bash
# Run one attack script as the agent user under Harbor against a scratch copy of the sweep task.
#   probes/redteam/sweep/container/run.sh <script.sh | reference | nothing> <name> [level] [seed]
# Prints the reward Harbor recorded. Output: runs/redteam/out-<name>/ (not committed).
set -e
cd "$(dirname "$0")/../../../.."
what=$1; name=$2; level=${3:-1}; seed=${4:-1}
rm -rf runs/redteam/t-$name runs/redteam/out-$name; mkdir -p runs/redteam
cp -r probes/sweep runs/redteam/t-$name
agent=oracle
case "$what" in
  reference) ;;
  nothing) agent=nop ;;
  *) cp probes/redteam/sweep/container/$what runs/redteam/t-$name/solution/solve.sh; chmod +x runs/redteam/t-$name/solution/solve.sh ;;
esac
sg docker -c "SWEEP_SEED=$seed SWEEP_LEVEL=$level SWEEP_SETTING=standard .venv/bin/harbor run -p runs/redteam/t-$name -o runs/redteam/out-$name -a $agent" > runs/redteam/out-$name.log 2>&1 || true
v=$(ls -d runs/redteam/out-$name/*/t-${name}__*/verifier 2>/dev/null | head -1)
echo "$name ($what, level $level, seed $seed): reward.txt=$(cat $v/reward.txt 2>/dev/null | tr -d '\n') reward.json=$(cat $v/reward.json 2>/dev/null | tr -d '\n') harbor=$(grep -o '"reward": *[0-9.]*' runs/redteam/out-$name/*/t-${name}__*/result.json 2>/dev/null | head -1)"
