# Break the Agent - by AfterQuery (Junction 2026)

The challenge brief as given to us. This is the source of truth for scope and judging.
**Read the update of 14 Nov at the end first: it fixes the stack and withdraws the model credits.**

## The challenge

Build a reinforcement learning environment that challenges today's best AI
agents, demonstrate real failure modes, and show that its rewards reflect real
progress.

## Introduction

Today's cutting-edge AI systems can solve Millennium Problems, discover new
drugs, and create entire production apps with a few lines of prompting. But they
still struggle in a wide variety of novel situations, ranging from everyday use
cases to niche, highly technical workflows. We ask: what should AI agents be
able to do that they still struggle with today?

At AfterQuery, we build environments for training and testing agents. The work
starts with choosing a problem worth learning, defining an action and
observation space, and defining a reward function that defines what success
looks like. Getting those pieces right is a heavy research and engineering
problem in itself.

For this challenge, we want to see your take on it. Build a world with something
interesting to learn. Find out where strong agents struggle, and whether your
reward actually encourages the behavior you intended.

## What to build

Choose a setting you find interesting and build an environment an agent can
interact with. It could be a game, a scientific simulation, a software task, a
real-world process, or something we haven't thought of. Explain why you chose it
and what an agent could learn there.

Your environment should have a clear goal, actions the agent can take, and a
reward you can check. Run a frontier agent in it and compare the results with a
stronger reference run your team can demonstrate and reproduce. We'll provide
the agent harness and model credits.

Show where the agent falls short and why. The challenge should come from the
decisions it needs to make, with access to the information and tools needed to
succeed. We'll also try to find shortcuts that earn a high score without
completing the task: reward hacking.

The setting and approach are yours to choose. We care about what makes the
environment useful for learning and what your experiments reveal.

## Optional stretch goal

Train a smaller model using experience from your environment and show whether it
improves.

## Judging rubric

We'll look at four things: how much room there is for the agent to improve,
whether its mistakes come from meaningful challenges, how well the reward holds
up to exploits, and how well the environment is built and the results can be
reproduced.

| Criterion | Points | Full points | Zero points |
|---|---|---|---|
| The gap | 30 | The frontier agent consistently scores below a stronger reference run your team demonstrates; both results can be reproduced across repeated runs | No measurable gap, or the claimed gap cannot be reproduced or checked against a demonstrated reference run |
| Meaningful difficulty | 30 | You can explain the agent's main mistakes and connect them to decisions in the task; the information and tools needed to do better are available to it | The gap comes from unfairly withheld information, trick wording, impossible timing, or broken tools |
| Reward integrity | 25 | The reward measures success at the task and holds up when judges try to exploit it; doing nothing or stopping early earns little or no credit; completing the task well remains the best way to score | An exploit, scoring loophole, or strategy that avoids the task earns a better score than successful play |
| Craft | 15 | The environment's rules and behavior make sense for the setting; judges can run the evaluation from your README with one command and reproduce your reported results | The environment only works in your demo, or judges cannot reproduce the evaluation |

## How judging runs

Each team gets a 10-minute demo. Judges then rerun the evaluation with the
standard harness: your reference run, three agent runs, a do-nothing baseline,
and a stop-early baseline. They also spend 15 minutes looking for reward
exploits. Scores are based on these runs.

Tiebreaker: if point totals are close, they favor a team that shows a smaller
model improving after training on experience from its environment.

## Starting points

Prompts, not a list of required features:

- Planning several steps ahead
- Exploring an unfamiliar system
- Using tools
- Managing limited resources
- Adapting when new information arrives

A small environment with a well-chosen challenge can be enough. Think about what
better play looks like, how you would measure it, and whether an agent could
increase its score without getting better at the task.

## What AfterQuery provides

- An open-source agent harness: Harbor running the OpenCode agent, which connects to our environment over MCP
- A scoring skeleton
- Frontier model API credits per team, to benchmark throughout the 48 hours
- On-site mentors for environment design reviews and reward testing: Daksh Raghuwanshi and Ved Vedere from AfterQuery's environments team
- Starter kit: harness documentation and the judging rubric

## Prizes

Top three teams: €3,000, €1,500 and €500. Members of the winning teams can go
straight to the final stage of AfterQuery's interview process (a work trial with
the environments team). Finalists also receive AfterQuery gear.

## Update from AfterQuery, 14 Nov 2026

Posted by the organisers in the challenge channel. Where it differs from the
brief above, this is the newer word.

### Required stack

"We need to run and compare every submission the same way, so everyone should
use the same stack."

- **Framework:** Harbor (https://github.com/laude-institute/harbor). The
  environment is a Harbor task: `instruction.md`, `task.toml`,
  `environment/Dockerfile`, `tests/` and `solution/`. Anything already
  containerised should convert easily.
- **Harness:** participants are urged to use the OpenCode harness when playing
  the environment, for example `harbor run -p ./my-task -a opencode -m [provider/model]`.
- **Reward:** the verifier writes **one score between 0 and 1** to
  `/logs/verifier/reward.txt`. Partial credit is welcome.

### Before you submit

- Include at least one Harbor run log with its score, showing a model playing
  through the environment. Playthroughs are also encouraged in the demo video.
- Write a short README: what the agent has to do, why it is hard, and how it is
  scored. AI-generated READMEs are accepted "but may communicate your
  environment's value poorly".
- Submit by the deadline.

### Inference credits

AfterQuery is **not** providing inference credits after all (demand was higher
than expected). Use the API credits provided by Google, OpenAI and Modal.

### What they are looking for

"Super cool simulations, environments, and some post-training experiments."

Questions go to the challenge channel or the AfterQuery booth.
