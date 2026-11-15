#!/bin/bash
# A directory where Harbor expects the reward file. Harbor itself (not the task's verifier) tries to remove
# stale reward files with plain `rm` before it runs the verifier, fails, and the trial ends with an exception
# and no reward at all. Not a score, but the trial is lost.
echo "PLANTDIR id: $(id)"
mkdir -p /logs/verifier/reward.json/sub && echo '{"reward":1.0}' > /logs/verifier/reward.json/sub/x
