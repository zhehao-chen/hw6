# Assignment 6 · Split it, measure it, decide

Model: OpenAI `gpt-4o-mini` (served as `gpt-4o-mini-2024-07-18`), the same for every run.

## Part A · The gates, before you build

**The roles you considered, and what each would need from the others mid-task.**

Four roles considered: an **investigator** (reads the issue, searches and reads code; holds `issues_read`, `code_search`, `code_read_file`, `code_run_tests`), a **writer** (applies the label, opens the draft PR, posts the comment; holds `issues_label`, `pulls_open`, `issues_comment`), a **reviewer** (checks the investigator's file before the writer acts; same reads as the investigator), and the **coordinator** (hands out issues, receives returns, dispatches writers; in code, not a model).

| Two roles | What one needs from the other while the task runs | How it would get it | What that costs |
|---|---|---|---|
| Investigator → writer | The label, the file, and one or two sentences of reason for the PR body and comment | Through the lead between rounds: the investigator's return becomes the writer's brief | Everything the investigator read and rejected is lost to the writer; a wrong file is written faithfully. One extra system prompt and tool list per issue |
| Writer → investigator | Nothing mid-task. Only if a write is refused (e.g. a PR whose file does not exist) would it need a corrected file | Would need a second round through the lead | A re-investigation round; I do not build it: a refused write is reported, not repaired |
| Investigator ↔ reviewer | The reviewer needs the investigator's file and evidence; the investigator would need the reviewer's objection to search again | Messages back and forth as they work, or rounds through the lead | Same model, same blind spots (slide 41): agreement is weak evidence, and every round is a full re-read of the file. Dropped |
| Investigator (issue *i*) ↔ investigator (issue *j*), batch only | Nothing: the five issues are unrelated, and none reads another's answer | — | — |
| Writer (issue *i*) ↔ writer (issue *j*), batch only | Nothing: each writes only to its own issue. The tracker is shared, but no two writers touch one issue | Shared state (the tracker), never read across issues | A wrong `issue` argument would be a write to another writer's issue: the combined check catches it |
| Coordinator ↔ every worker | A structured return (the contract) from each investigator; a done/refused from each writer | Return values, between rounds | A return can only carry what its fields allow, so `could_not_determine` and `not_searched` are explicit |

- **For one issue:** the work is one chain: read → search → read file → decide → label → PR → comment. The writer needs the investigator's whole finding, and needs nothing else; there is nothing to run at once. What a split adds is one seam (the return), and the writer's acts depend entirely on what crosses it.
- **For a batch of five:** five such chains with no arrows between them. The only arrows are coordinator → investigator *i* → coordinator → writer *i*. The five investigators can run at once, and so can the five writers.

**What each role returns, and what it is unable to say.**

| Role | Returns | Unable to say |
|---|---|---|
| Investigator | `result` {issue, label, file, evidence, pr_summary}; `status` found / candidate / out_of_budget; `searched` and `calls_used` (filled by code from its own tool calls); `not_searched`; `could_not_determine` | Whether a file it never read is the real cause; whether the reporter's suggested file was checked unless it is in `searched`; anything about another issue |
| Writer | Nothing structured: its writes are read back from the tracker by the combined check | Whether the finding it wrote was right; it cannot read code |
| Coordinator | The combined check's violations | Whether any label or file is *correct* (it has no answer key); only whether the end state is consistent |

**The sketch.** Arrows are things one role needs from another mid-task; dotted lines are writes to the shared tracker.

```
ONE ISSUE                                   BATCH OF FIVE (i = 1..5, no arrows between columns)

  coordinator (code)                          coordinator (code) ──────────────────────────┐
     │ brief: issue #n                           │ brief #1   │ brief #2   ...   │ brief #5   │
     ▼                                           ▼            ▼                  ▼            │
  investigator  (reads only)                  invest.#1    invest.#2   ...   invest.#5        │  run at once
     │ return: contract (label, file,            │            │                  │            │
     │   searched, could_not_determine)          ▼            ▼                  ▼            │
     ▼                                        coordinator: validate each return; reject+re-ask│
  coordinator: validate, or reject              │ finding #1  │ finding #2  ...  │ finding #5 │
     │ brief: label, file, summary              ▼             ▼                  ▼            │
     ▼                                        writer #1     writer #2   ...   writer #5       │  run at once
  writer  (label, PR, comment only)              ┊             ┊                  ┊            │
     ┊ label → PR → comment                      ┊ tracker, issue #1 only ...     ┊ #5 only    │
     ▼                                           ▼                                ▼            │
  tracker ──► combined check (reads tracker)   tracker ──────► combined check over all five ◄─┘
```

**The four gates** (slide 46), in order, stopping at the first no.

| Gate | One issue | Why | A batch of five | Why |
|---|---|---|---|---|
| 1. The parts work mostly without talking | **fail** | The only split available is stage-by-stage of one finding: the writer's every act is a function of the investigator's label and file. It is "found, then fixed" (slide 49): a pipeline with one seam, not parts | **pass** | Five unrelated issues; no issue's investigation reads another's. The only traffic is lead ↔ worker between rounds |
| 2. Each part's result can be checked on its own | not_reached | — | **pass** | Each issue has its own grounded rule: one comment with label and file, that label on the issue, one PR naming the file or none. The combined check still runs over all five, because parts can pass and the whole be wrong (e.g. a PR on the wrong issue) |
| 3. A team buys what one agent cannot get more cheaply | not_reached | — | **pass**, for parallelism only | One loop runs the five issues one after another; five investigators can run at once, so wall-clock can fall toward the slowest issue. Context isolation does *not* pass this gate: one agent gets fresh contexts more cheaply with attempts per issue (slide 12). Specialisation by tool surface is real (an investigator cannot write, a writer cannot wander off into the code) but one agent with a hook gets most of that safety already |
| 4. The result is worth the multiplier | not_reached | — | **fail** (on paper) | The daily triage is a batch job with no deadline in minutes: wall-clock is the one benefit that passed gate 3, and it is worth little here. If a split also passed more batches, that would be worth paying for, but gate 3 says one agent can buy the same room more cheaply. Part C measures whether this holds |

- **The benefit you are trying to buy, and the condition it needs:** *parallelism* on the batch: wall-clock time for five issues close to one issue's. Its condition is that the parts be truly independent, which the batch's five unrelated issues meet and one issue does not. As a side effect, I also take *specialisation by tool surface* (the investigator holds no write tool; the writer holds no read tool), whose condition — truly different requirements — the two halves of the daily task do meet: one half only reads, the other only writes. I do not claim context isolation as the benefit, since one agent can buy it more cheaply.
- **Your prediction, as committed in `reports/PREDICTIONS_06.md`, and its commit:** commit `f782fb6`, pushed before any run of either arm. It predicted M at about 1.3× S's tokens on single tasks and 0.6× on batches; passes about equal on single tasks; M ahead by 1–2 batch passes; and S-plus as good as M on both kinds. Measured: 0.92× and 0.63×; M 5/18 against S 2/18 on single tasks; 0/6 for every arm on batches; S-plus 3/18 and 0/6.

## Part B · The split

All of it is on `lab-06-split` (tag `lab-06-split-final`), never merged: `ways/split.py`, `split/roles.py`, `split/guards.py`, `split/contract.schema.json`, `prompts/investigator.md`, `prompts/writer.md`.

- **The coordinator and the roles, and the tools each holds:**
  - *Coordinator* (`ways/split.py`, `Coordinator`): code, not a model, so it spends no tokens. It gives each issue to an investigator, validates every return, writes accepted findings to a versioned board, gives each finding to a writer, and checks the end state. On a batch the five investigators run at once, and then the five writers.
  - *Investigator*, one per issue (`split/roles.py`, `InvestigatorSurface`): `issues_read`, `code_search`, `code_read_file`, `code_run_tests`, and a local `return_finding` tool (strict). It can read everything and write nothing.
  - *Writer*, one per issue (`WriterSurface`, wrapped in `Disclosing`): `issues_label`, `pulls_open`, `issues_comment`. Each write must name the writer's own issue, or it is refused before the registry. It can write and read nothing.
  - Every name outside a role's surface is refused locally. Every name inside it still goes through `ctx.tools`, which is the registry with the Assignment 5 hook. The disclosure line goes on every comment in `with_disclosure`, the one function every comment passes before the registry.
- **Why they split by tool surface:** the daily task has two halves with different requirements: one only reads, the other only writes. Splitting by surface changes what each agent *can* do wrong. The investigator cannot post a comment before it has decided. The writer cannot wander back into the code and change the file. A writer cannot write to another writer's issue. I did not build a reviewer: on the same model it shares the investigator's blind spots (slide 41), and its agreement would be weak evidence.
- **The return contract, field by field** (`split/contract.schema.json`, validated with `harness.schema.errors` on every return):

  | Field | Type | From |
  |---|---|---|
  | `result` | `{issue: int, label: enum, file: str, evidence: str, pr_summary: str}`, no extra keys | the model, through `return_finding` |
  | `status` | `found` \| `candidate` \| `out_of_budget` | the model |
  | `searched` | list of str: every `query` the worker searched and every `path` it read, each once | **code**: `InvestigatorSurface._note`, counted from the worker's own calls as they pass through its surface |
  | `not_searched` | list of str | the model |
  | `calls_used` | int: the worker's own calls to the registry's tools before it returned | **code**, as above |
  | `could_not_determine` | list of str, `[]` when nothing | the model |

  The model is never shown `searched` or `calls_used` as fields it can fill. If it sends them anyway, they are dropped and overwritten. Nothing the model sends is repaired. A return that breaks the schema is recorded as `worker_return` with `valid: false` and its errors, is never acted on, and goes back to the worker as a tool error asking it to call again. Every return, valid or not, is recorded on the coordinator's lines before it is acted on.
- **Each worker's share of the budget, and what is held back:** `ctx.budget` is the whole run's ceiling: B per issue, or 5B on a batch. Each issue gets `budget / n`. Of that, the investigator may spend 60%, as its `run_loop` `max_tokens`, with 10 steps. The writer may spend 20%, with 5 steps. The last 20% is held back for one re-investigation (`investigator-<n>-r2`), given what is left of the 80%, when the first investigator ends without a valid return. All agents' clients send through the run's one client, so the run's hard ceiling holds across them all.
- **The five checks, where each is in the code:**
  1. *Return contract:* `InvestigatorSurface._return` (split/roles.py) validates every return against the schema and records `worker_return`. An invalid return is rejected and the worker is asked again.
  2. *Deadlock detection:* `WaitGraph` (split/guards.py). Every wait is a `wait` trace line and an edge in the graph, released when the worker returns. A wait that closes a cycle is returned, and `victim()` stops one worker in it (never the coordinator), with a `worker_stopped` line. My roles never wait on each other, so live runs never cycle. The recorded deadlock is caught at turn 1.
  3. *Combined result:* `check_combined` (split/guards.py) runs after the last write, on `end_state(tracker, run_id, task)`, never on what the workers said. The rules are set before the run: one comment with label and file lines, exactly that label, and one PR naming the file, or none. It is recorded as `combined_check`.
  4. *Idempotency and compare-and-set:* the tracker writes keep Assignment 3's derived keys. The state agents share, the findings board writers read from, is a `SharedState`, written only by compare-and-set against the version read. The recorded lost update is refused: B's write from its stale read returns False, and A's fix stays.
  5. *One trace:* every agent comes from `ctx.agent(...)`, so every `model_call` and `tool_call` line carries `agent` and `parent` (the coordinator's parent is none), and the coordinator writes an `agent_tokens` line whose per-agent sums add to `run_end`.

## Part C · Measured

**The five constants** (slide 59), identical in every one of the 72 `run_start` lines:

| Constant | Value |
|---|---|
| Model | `gpt-4o-mini` (served as `gpt-4o-mini-2024-07-18`) |
| Tools | `schemas_sha` `703c0002892f27ec` |
| Budget | B = 250,000 tokens per issue (`agent/bounds.yaml`), so a ceiling of 250,000 per single task and 1,250,000 per batch for arms S and M. S-plus's budget per task is M's mean spend on that task |
| Evaluator | `checks_sha` `55abcd67e6a3b208`; reviewer `scripted:approve-all` |
| Task set | `batch-a`, `batch-b`, `one-4402`, `one-4403`, `one-4405`, `one-4406`, `one-4409`, `one-4413` |

Every arm ran with `--jobs 4`. No run hit a rate limit, and none was redone.

**The results** (`results/runs_06.jsonl`, from `eval/check_task.py` and the `run_end` lines):

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | 2 / 18 | 0 – 1 | 0 | 36,297 | 11.0 |
| S | batch | 0 / 6 | 0 – 0 | 0 | 245,653 | 45.2 |
| M | single | 5 / 18 | 1 – 2 | 1 (one-4413) | 33,285 | 18.8 |
| M | batch | 0 / 6 | 0 – 0 | 0 | 155,308 | 29.3 |
| S-plus | single | 3 / 18 | 1 – 1 | 0 | 30,870 | 15.3 |
| S-plus | batch | 0 / 6 | 0 – 0 | 0 | 144,760 | 75.5 |

Per task: passes out of 3, then mean tokens. On batches, issues passed out of 15 are in brackets.

| Task | S | M | S-plus |
|---|---|---|---|
| one-4402 | 0 · 28,430 | **2** · 25,018 | 0 · 23,564 |
| one-4403 | 0 · 40,620 | 0 · 36,779 | **1** · 34,774 |
| one-4405 | 0 · 35,724 | 0 · 30,165 | 0 · 25,860 |
| one-4406 | 0 · 50,808 | 0 · 57,735 | 0 · 56,125 |
| one-4409 | 0 · 26,833 | 0 · 22,771 | 0 · 21,041 |
| one-4413 | 2 · 35,365 | **3** · 27,241 | 2 · 23,855 |
| batch-a | 0 (10/15) · 190,572 | 0 (6/15) · 132,061 | 0 (7/15) · 124,865 |
| batch-b | 0 (7/15) · 300,734 | 0 (9/15) · 178,554 | 0 (6/15) · 164,655 |
| **batch issues** | **17 / 30** | **15 / 30** | **13 / 30** |

gpt-4o-mini is weak at this task: every arm misses 4405, 4406 and 4409 on every run, mostly by naming a plausible neighbour of the right file. Each pass count is small, so a difference of two or three runs is within the sweep-to-sweep spread.

- **Your multiplier (M over S), beside the lecture's 15×:** **0.92× on single tasks and 0.63× on batches.** The split spent *less* than one agent on both kinds. The lecture's ~15× is Anthropic's figure for multi-agent systems against a *chat*, on their own workload, with one agent at ~4× a chat. On that scale, mine is one design at ~0.9× and ~0.6× of *one agent*, on eight tasks of one task set, so the two numbers measure different things. The reasons for mine: my coordinator is code and spends nothing; each investigator is offered 5 tool schemas and each writer 3, where the single agent is offered 10 on every call; and on a batch the single agent re-sends all five issues' reads on every later step, while each investigator starts fresh. I predicted 1.3× and 0.6×: the batch figure held, but the single figure did not, because I counted the writer's extra context and forgot the cheaper tool lists.
- **Whether S-plus's spend matched M's in fact, task by task:** yes, slightly under on every task: batch-a −5%, batch-b −8%, 4402 −6%, 4403 −5%, 4405 −14%, 4406 −3%, 4409 −8%, 4413 −12%. Overall that is −7% on single tasks and −7% on batches. The shortfall comes from S-plus's stopping rule: it starts no attempt that would, on average, carry an issue past its share. Since M spent less than S, S-plus ran at a *smaller* budget than S actually used.

**Slide 18's three questions**, for each kind of task.

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | **No.** M 33,285 against S 36,297 (0.92×) | **No.** M 155,308 against S 245,653 (0.63×) |
| Does spending more raise the score? | **No.** One agent at about 36k tokens per task (S) passed 2/18; at about 31k (S-plus) it passed 3/18. The extra spend bought nothing, and the split passed the most on the second-lowest spend | **No.** One agent passed 0/6 at 246k and 0/6 at 145k. Per issue, more spend went with *more* issues passed (17/30 against 13/30), but no batch passed at either budget |
| Given the same budget, did one agent do as well? | **No, narrowly.** S-plus 3/18 against M 5/18 | **Yes.** S-plus 0/6 against M 0/6. Per issue, S-plus 13/30 against M 15/30, and S (more spend, one context) 17/30 |

- **Reading it as slide 18 reads the 90.2%:** any no credits the design, because extra spend can no longer explain the win. On single tasks all three answers are no. The split did not spend more, and it passed 5 against 2 and 3. The win cannot be spend. But it is two to three runs out of 18, on two tasks (4402: 2 against 0 and 0; 4413: 3 against 2 and 2). The sweep ranges almost touch (M 1–2 per sweep, S-plus 1–1, S 0–1), and a Fisher exact test of 5/18 against 2/18 gives p ≈ 0.40, and against S-plus's 3/18 p ≈ 0.69. The design is credited by the rule, not established by the data. On batches, the split did not spend more, and one agent did as well at its spend: no arm passed a batch. The split's measured benefits are 0.63× the tokens and 0.65× the wall-clock of arm S. Of these, S-plus matches the tokens (fresh contexts, one agent), and only the wall-clock is the split's own (29 s against S's 45 s and S-plus's 76 s).
- **What you would have claimed from arms S and M alone, and what you claim now:** from S and M alone, I would have written: "the split passes 2.5× as many single tasks at 8% fewer tokens, and triages a batch at 37% fewer tokens and 35% faster." Now I claim less. On single tasks, the split's edge is small, within the noise of 18 runs, and not explained by spend. On batches, the token saving is fresh context, which one agent buys too (S-plus 145k against M 155k). The split does not pass more issues: the single agent in one context passed the most (17/30). The one benefit only the split shows is wall-clock on the batch, which is what gate 3 predicted and gate 4 said is worth little here.

**Every arm M run that failed** (19 of 24). For each run I read the trace: what each agent read, wrote and waited on, and the first thing that went wrong. The coordinator wrote no shared state except the findings board (one writer per key, never contended: no `cas_refused`). No wait ever closed a cycle (no `worker_stopped`). The combined check passed on every run where writes happened, so no run shows divergence between the investigator's return and what the writer wrote.

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| split-batch-a-s01-7604ff | 5 investigators read issues and code in parallel; the coordinator waited on each and got 5 valid returns; 5 writers wrote exactly those findings | Investigator-4412 returned `bug, src/api/health.ts` (status found) for a question; 4420 and 4423 also returned wrong files. The writers wrote them faithfully | none | task_verification |
| split-batch-a-s02-92cd95 | as above | The same three wrong findings (4412, 4420, 4423), returned `found` | none | task_verification |
| split-batch-a-s03-374b0f | as above | The same three wrong findings | none | task_verification |
| split-batch-b-s01-d4b60d | as above | Investigator-4431 returned `src/exportUtils.ts`; 4434 returned `src/api/uploads.ts` | none | task_verification |
| split-batch-b-s02-ce5ea7 | as above; investigator-4431 ended on its turn limit after returning | Investigator-4424 returned the wrong file `src/api/reports.ts`; 4431 also wrong; 4426 returned `question` *with* a file, and the writer opened a PR for it | none | task_verification |
| split-batch-b-s03-926241 | as above | Investigator-4431 returned `bug, src/exportUtils.ts` for a feature in `src/util/strings.ts` | none | task_verification |
| split-one-4402-s02-44efa6 | Investigator read, returned; writer wrote | Investigator returned `src/ingest/schema.ts`, status found | none | task_verification |
| split-one-4403-s01-cc9b74 | Investigator searched for control characters in `src/**/*.py` (the repository is TypeScript) for 10 turns; it hit the turn limit with no return. The coordinator re-investigated with the held-back share, and `-r2` did the same. The coordinator had no valid return, so it wrote nothing | The investigator's stopping rule: a 10-step limit, with nothing in the loop forcing a return on the last step, so the `out_of_budget` status the contract offers was never used | none | system_design |
| split-one-4403-s02-73effe | Investigator returned; writer wrote | Investigator returned `question` *with* file `src/export/csv.ts`, which the contract allows. The writer, told a file, opened a PR on a question | none | system_design |
| split-one-4403-s03-7531d0 | as s02 | The same: `question` with a file, which the contract does not forbid | none | system_design |
| split-one-4405-s01-e717e6 | Investigator returned; writer wrote | Wrong file `src/api/reports.ts`, status found | none | task_verification |
| split-one-4405-s02-f74c31 | as above | The same wrong file | none | task_verification |
| split-one-4405-s03-40a6ef | as above | The same wrong file | none | task_verification |
| split-one-4406-s01-e4564b | Investigator hit its turn limit just after returning; writer wrote | Wrong file `src/export/xlsx.ts` | none | task_verification |
| split-one-4406-s02-bd2819 | Investigator read `csv.ts` and `exportUtils.ts` and searched for 10 turns with no return; `-r2` did the same; nothing was written | The stopping rule, as in 4403-s01 | none | system_design |
| split-one-4406-s03-8830eb | Investigator returned; writer wrote | Wrong file `src/api/reports.ts` | none | task_verification |
| split-one-4409-s01-98c9b5 | Investigator returned; writer wrote | `docs, docs/CONFIG.md` where the answer is `README.md` | none | task_verification |
| split-one-4409-s02-72e7cc | as above | The same | none | task_verification |
| split-one-4409-s03-5d42ac | as above | The same | none | task_verification |

No failure is a lost update, write skew, deadlock or misalignment. Every one starts inside one agent, the investigator, and then crosses the seam intact. 15 of the 19 are a wrong finding that nobody checked (task verification). The investigator says `found` on the strength of its own read, and the combined check, which needs no answer key, cannot tell a consistent wrong answer from a right one. 4 are system design: two returns the contract should have refused (`question` with a file), and two runs where the stopping rule let the investigator run out of turns without returning. In those two runs no `worker_return` was recorded at all, which costs the "at least one return in every run" check its 2 points. I did not fix either and re-measure, because that would be tuning the split on the measurement tasks after seeing them fail.

## Part D · The decision

- **One issue: one agent.** Gate 1 failed on paper: the writer is a function of the investigator's finding. The measurement agrees: every failure is the investigator's, passed faithfully across the seam. The split's 5/18 against 3/18 at matched spend is credited by slide 18's rule, but it is two runs, p ≈ 0.4, and the split was slower (18.8 s against 11.0 s).
- **A batch of five: one agent.** The batch passes gates 1–3, and the split was 35% faster and spent 37% fewer tokens than arm S. But no arm passed a batch, the single agent passed the most batch issues (17/30 against 15/30), and S-plus shows the token saving is fresh context, not the split. What only the split buys is about 16 seconds on a job with no deadline.
- **The condition that would reopen it:** a batch of at least five separate issues, each with its own grounded check, run three times with the five constants held and an S-plus arm at the split's measured spend. The split passes more batch tasks than both one-agent arms, or more batch issues than S-plus by at least 5 in 30. Or: the daily batch acquires a wall-clock deadline that one agent misses and the split meets. My batch result speaks to slide 49's condition directly, but at this model's accuracy (no batch passed in 18 batch runs), it cannot show a split winning. A stronger model, which passes batches, is the first thing to retest.
- **The record:** `decisions/0006-topology.md`.

AI assistance: Claude Code (Claude Opus 5.5) wrote the split (`ways/split.py`, `split/`), `ways/splus.py`, `eval/results_06.py`, the roles' prompts, and the drafts of this report, the prediction and the decision record, and ran the 72 runs. I checked the guard replays with `python checks/check_06.py --here` and the scripted runs. I recomputed every number in Part C from `results/runs_06.jsonl` and `make check-06`, and read each failed arm M run's trace for the failure table.
