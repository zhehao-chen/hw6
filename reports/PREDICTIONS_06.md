# Assignment 6 · Predictions, before any run of the split

Written on main after Part A and before any run of either arm, so no measurement could
shape it. Model: gpt-4o-mini. B = 250,000 tokens per issue (agent/bounds.yaml), 5B for a batch.

The split I will build: a coordinator in code; per issue, one investigator (read tools only,
returns a structured contract) and one writer (label, PR and comment only). On a batch the
five investigators run at once, then the five writers.

## Tokens: arm M over arm S, per task

- **Single tasks: about 1.3×.** The investigator spends about what the single agent spends
  on its reads, and the writer adds a second, smaller context (its own system prompt, tool
  list and the brief) for three writes. The return tool and a rejected return now and then
  add a little.
- **Batch tasks: about 0.6×.** The single agent carries all five issues in one context, so
  each later step re-sends everything read for the earlier issues; its spend grows faster
  than linearly. The split starts each issue fresh, so its spend is about five times one
  issue's, about 1.3 × 5 single-issue runs, which I expect to be well under one five-issue
  context.

## Passes: arm S against arm M

- **Single tasks (18 runs each): about the same, within ±2 passes.** I expect each near
  12/18. The writer cannot fix a wrong file, and the investigator does the same reads the
  single agent does; the split adds a seam, not ability. If anything, the split loses one or
  two runs to a writer that mis-copies the brief.
- **Batch tasks (6 runs each): the split ahead by about 1 to 2 batch passes**, e.g. S 0–1/6
  against M 1–3/6. A batch passes only if all five issues pass, and the single agent's
  accuracy on issues four and five falls as its context fills. Per issue, I expect the split
  about 10 points higher on batches.
- **Wall-clock:** the split slower on single tasks (two agents in sequence), and about 2–3×
  faster on batches (five at once).

## Arm S-plus: one agent given the split's spend

- **Single tasks: yes, as well as the split** (and as well as arm S), since the split did not
  win there to begin with.
- **Batch tasks: yes, as well as the split, or within one batch pass.** S-plus's attempts give
  each issue a fresh context, which is the room the split buys, and its vote over attempts
  adds a little accuracy the split does not have. If the split's batch win is real, I expect
  it to be explained by fresh contexts, not by having two roles, so S-plus should close it.
  What S-plus cannot match is the split's batch wall-clock.
