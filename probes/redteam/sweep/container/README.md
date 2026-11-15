# Container-side red-team scripts for probes/sweep (2nd pass)

Each script is dropped in as `solution/solve.sh` of a **scratch copy** of the task and run
with `-a oracle`, which runs it as the unprivileged user `agent` with the exact rights the
real OpenCode agent has (confirmed: `id` prints `uid=1001(agent)`). The only oracle-specific
difference is that `-a oracle` also bind-copies `solution/` into the container; a real
`-a opencode` agent does **not** get `/solution` (see report).

How to run one (from repo root):

    rm -rf runs/redteam/t-X && cp -r probes/sweep runs/redteam/t-X
    cp probes/redteam/sweep/container/<script>.sh runs/redteam/t-X/solution/solve.sh
    chmod +x runs/redteam/t-X/solution/solve.sh
    sg docker -c "SWEEP_SEED=1 SWEEP_LEVEL=1 SWEEP_SETTING=standard \
        .venv/bin/harbor run -p runs/redteam/t-X -o runs/redteam/out-X -a oracle"
    # recorded reward: the "Reward" table at the end of the harbor log, and
    # runs/redteam/out-X/*/t-X__*/verifier/reward.{txt,json}

Honest references (same harness): oracle reference level 1 = **1.0000**; do-nothing (`-a nop`) = **0.0000**.

| script | what it does | measured Harbor reward |
|---|---|---|
| `race.sh` | leftover writers (non-respawning) flood reward.txt/json | 0.0000 (HELD — kill loop wins) |
| `race2.sh` | **self-respawning** writers flood reward.txt + reward.json | **1.0 once; RewardFileEmptyError (grader crash) 3x; 0.0 once** over 5 runs |
| `race3.sh` | self-respawning writers, reward.json only | RewardFileEmptyError (grader crash) |
| `stopearly.sh` | one HTTP call then quit | 0.0000 (HELD) |
| `leak.sh` | curl /log, /score, cameras, list files, env | 0.0000; see report for what leaked |
| `impersonate.sh` | try hosts/preload/tests/docker-sock/sudo/bind 8000 | 0.0000 (all tamper denied; only local bind of :8000 succeeds, which does not hijack the sidecar) |

CONFIRMED EXPLOIT (before the fix of 14 Nov 23:40): `race2.sh` and, reliably, `race4.sh`: background processes that keep restarting each other outlive
verifier's bounded kill loop and plants `/logs/verifier/reward.json` (which the task never
writes and Harbor prefers over reward.txt), scoring 1.0 vs honest 0.0, or crashing the grader
(RewardFileEmptyError). See the red-team experiment file for the full writeup and fix.

## After the fix to `probes/sweep/tests/test.sh` (14 Nov, 23:40)

The verifier now takes the log directory away from the agent user first, kills every process of that user
with one signal, empties the directory, and writes `reward.json` as well as `reward.txt` (0 if anything fails).
Rerun with `probes/redteam/sweep/container/run.sh <script.sh | reference | nothing> <name> [level] [seed]`:

| run | Harbor reward before the fix | after the fix |
|---|---|---|
| `race4.sh` (restarting writers, rename into place) | 1.0 in 3 of 3 | 0.0 in 2 of 2 |
| `race5.sh` (the same, and kills the verifier's helper process) | not run | 0.0 |
| `plant.sh` (links, named pipe, read-only tree, planted reward.json) | not run | 0.0 |
| do-nothing (`nothing`), levels 1 and 2 | 0.0 | 0.0 |
| scripted reference (`reference`), level 1, seed 1, standard setting | 1.0 | 1.0 |

Still open, in Harbor and not in the task: `plantdir.sh` (a directory named `reward.json`) makes Harbor's own
clean-up fail before the verifier runs; the trial ends with an exception and no reward. No score is gained.
