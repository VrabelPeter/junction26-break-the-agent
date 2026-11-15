---
title: Probe A v2 (orbital ops with filter learning): anchors and Kimi
status: failed
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T04:04+02:00
finished: 2026-11-14T04:07+02:00
commit: 1d5f7b8
command: .venv/bin/harbor run -p probes/orbital2 -a oracle|nop|opencode -m verda/kimi-k3-1-pro ... -e modal -o runs/orbital2
headline: Stopped on request before the Kimi run finished; reference 0.909 under Harbor, no agent score for v2
---

## Hypothesis

Version 2 after v1 showed no gap: 4 operations per window, detector filters whose quality per target class must be learned from noisy results that arrive at downlink (and shift once), single-use remedies with a price. Seed 101. Question: does Kimi K3.1 Pro now fall short of the scripted learning reference, and by how much?

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Results

- `-a oracle` (scripted learning reference) on Modal, seed 101: reward 0.9091, as in-process.
- The Kimi run was **stopped at Peter's request before it finished** (change of direction towards a robotics environment); no agent score exists for version 2.
- In-process anchors on 40 held-out seeds (101 to 140): fixed filter 1015, naive try-each-once learner 1252, learning reference 1331, privileged ceiling 1522.

## Takeaways

Unanswered: whether a strong model falls short on version 2. The in-process numbers say the learning mechanic alone is worth about 6% between a naive and a careful learner. To resume: the two commands in the frontmatter, with `--job-name kimi-1`.

Note, 14 Nov: the orbital probe code (`probes/orbital`, `probes/orbital2`) was removed from the tree at Peter's request after the change to a robotics environment. It is in git history; the last commit that contains it is `a1ac3bc` (`git checkout a1ac3bc -- probes/orbital probes/orbital2` brings it back).
