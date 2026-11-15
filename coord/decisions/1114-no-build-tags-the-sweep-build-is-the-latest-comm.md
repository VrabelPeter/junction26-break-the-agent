---
title: The build is the latest commit on main; tags mark task variants and simulator ablations only
status: accepted
by: peter
date: 2026-11-14T23:18+02:00
---

## Context

Frederik's message 1114-1957 asked whether the `/log` change after `sweep-frozen-1` (commit 9b7b98c: seed and level
hidden from the agent's container during play) needs a new tag. Peter, 14 Nov 23:20, revised 23:35.

## Decision

- **The build is the latest commit on `main`.** Every run records its commit. Ordinary fixes and changes that leave
  the agent's task as it was (same observations, tools, physics, what success needs, scoring) get no tag. The `/log`
  change is one of these: it was not meant to change anything, and runs before and after it are comparable.
- **A tag marks a variant**, used when experimenting with:
  - a different task structure: something changed in how the task runs or in what success requires;
  - a simulator change made for an ablation.
  Name it after the variant (for example `sweep-ablation-no-depth`), say in the experiment which tag the runs used,
  and never mix runs from different variants in one comparison without saying so.
- `sweep-frozen-1` stays in git as the marker of the arm fix; it is not moved.
- Unchanged: after any change to the task, its server, its instruction or the scoring, a passing smoke test before a
  long run (CLAUDE.md).

## Consequences

Comparison pages and tables group runs by the commit line of `main` from the arm fix on, and show variant runs
separately and labelled with their tag.
