# 0006 · Topology: RepoMind stays one agent

- **Status:** decided, 2026-11-13. The split was built and measured on branch `lab-06-split` (tag `lab-06-split-final`) and is not merged.
- **Evidence:** `reports/LAB_06.md`, `reports/LAB_06.json`, `results/runs_06.jsonl`, and the 72 traces in `runs/`.

## What was tested

The question: should RepoMind's daily triage (read an issue, find the file, label it, open a draft PR, comment) be done by several agents instead of one? It was asked for two kinds of task: one issue, and a batch of five unrelated issues in one run.

The split: a coordinator written in code, plus two roles per issue, split by tool surface. An **investigator** holds only the read tools and returns a structured contract (`result`, `status`, `searched`, `not_searched`, `calls_used`, `could_not_determine`), which the code validates against a JSON schema. A **writer** holds only the label, PR and comment tools, each scoped to its own issue. On a batch, the five investigators run at once, then the five writers. It also has the five cheap checks: the contract, deadlock detection, a combined check of the tracker's end state, compare-and-set on shared state, and one trace for all agents.

**Gate verdicts, before building** (slide 46):

| Gate | One issue | Batch of five |
|---|---|---|
| 1. Parts work mostly without talking | fail: the writer is a function of the investigator's finding | pass: five unrelated issues |
| 2. Each part checkable on its own | not reached | pass: each issue has its own grounded rule |
| 3. A team buys what one agent can't get more cheaply | not reached | pass, for parallelism only; one agent gets fresh contexts more cheaply |
| 4. Worth the multiplier | not reached | fail on paper: wall-clock is worth little for a daily batch |

**The prediction** (`reports/PREDICTIONS_06.md`, commit `f782fb6`, pushed before any run): M at about 1.3× S's tokens on single tasks and 0.6× on batches; passes about equal on single tasks; M ahead by 1–2 batch passes; S-plus as good as M on both.

## What was found

The five constants were held in every run: model `gpt-4o-mini`; tool schemas `703c0002892f27ec`; budget B = 250,000 tokens per issue (5B per batch), with S-plus given M's measured spend per task; evaluator `55abcd67e6a3b208` with reviewer `scripted:approve-all`; and the eight tasks of `fixtures/tasks6`. Each arm ran three sweeps, 24 runs, with `--jobs 4`.

| Arm | Single: passes | Single: mean tokens | Single: wall (s) | Batch: passes | Batch: issues passed | Batch: mean tokens | Batch: wall (s) |
|---|---|---|---|---|---|---|---|
| S, one agent | 2 / 18 | 36,297 | 11.0 | 0 / 6 | 17 / 30 | 245,653 | 45.2 |
| M, the split | 5 / 18 | 33,285 | 18.8 | 0 / 6 | 15 / 30 | 155,308 | 29.3 |
| S-plus, one agent at M's spend | 3 / 18 | 30,870 | 15.3 | 0 / 6 | 13 / 30 | 144,760 | 75.5 |

**The multiplier (M over S): 0.92× on single tasks and 0.63× on batches.** The lecture's ~15× is Anthropic's figure for multi-agent systems against a chat, on their own workload. Mine is one design against one agent, on eight tasks. The split spent less because its coordinator is code, its roles are offered 5 and 3 tools instead of 10, and its investigators start fresh rather than re-sending earlier issues.

**Slide 18's three questions:**

| | One issue | Batch of five |
|---|---|---|
| Did the split spend more? | no (0.92×) | no (0.63×) |
| Does spending more raise the score? | no (one agent: 2/18 at 36k, 3/18 at 31k) | no (one agent: 0/6 at 246k and at 145k) |
| At the same budget, did one agent do as well? | no, narrowly (3/18 against 5/18; Fisher p ≈ 0.69) | yes (0/6 against 0/6; 13/30 issues against 15/30) |

**The failures.** All 19 failed split runs start inside the investigator. 15 are a wrong file or label returned as `found` and written faithfully (MAST: task verification). 4 are system design: two `question` returns carrying a file, which the contract should refuse, and two investigators that hit their turn limit without returning. None is a lost update, write skew, deadlock or misalignment. The combined check passed on every run that wrote anything.

## The decision

- **One issue: one agent.** The design is credited by slide 18's rule, since the split won without spending more. But the win is two or three runs of 18, on two tasks, and well within the noise. The split is slower, and gate 1 fails: the seam adds a place to lose information and no place to catch the investigator's error.
- **A batch of five: one agent.** No arm passed a batch. One agent in one context passed the most batch issues. S-plus reproduces the split's token saving with fresh contexts and no roles. The only benefit the split alone delivered is about 16 seconds of wall-clock per batch, on a job with no deadline.

## What would reopen it

Reopen this decision if either of these happens:

1. **On batches, the split wins at matched spend.** The test: a batch of at least five separate issues, each with its own grounded check, run three times with the five constants held and an S-plus arm given the split's measured spend. The split must pass more batch tasks than both one-agent arms, or pass at least 5 more batch issues in 30 than S-plus. This is slide 49's condition.
2. **The daily batch gets a deadline.** It acquires a wall-clock deadline that one agent misses and the split meets.

My batch result speaks to the first condition but cannot settle it. At gpt-4o-mini's accuracy, no arm passed any of 18 batch runs, so a split could not show a batch win here. The first rerun should use a model that passes single tasks reliably.

## What we lose either way

- **By splitting, we lose:**
  - the investigator's rejected leads: the writer sees only the contract;
  - a place where errors cross unchecked: every failure here crossed the seam intact;
  - a stopping rule per role that can drop a whole issue: two runs wrote nothing;
  - a contract to keep in step with the task (`question` with a file got through);
  - more code to own: guards, waits, a findings board;
  - speed on a single issue: 18.8 s against 11.0 s.
- **By not splitting, we lose:**
  - about a third of the batch's wall-clock and tokens: one agent can recover most of the tokens with a fresh context per issue, but not the wall-clock;
  - tool-surface separation: one loop holds both the reads and the writes, so the hook, not the surface, is what stops a premature comment;
  - a possible small edge on single tasks, which this sample could neither confirm nor rule out.

ARCHITECTURE.md is unchanged: RepoMind remains one agent, and that is this assignment's result.
