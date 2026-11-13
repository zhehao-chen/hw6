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
- **Your prediction, as committed in `reports/PREDICTIONS_06.md`, and its commit:** see that file; its commit hash is given in Part C.

## Part B · The split

- The coordinator and the roles, and the tools each holds:
- Why they split by tool surface:
- The return contract, field by field, and which fields come from the worker's tool calls:
- Each worker's share of the budget, and what is held back:
- The five checks, where each is in your code:

## Part C · Measured

**The five constants** (slide 59): model, tools, budget, evaluator, task set.

**The results.**

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | | | | | |
| S | batch | | | | | |
| M | single | | | | | |
| M | batch | | | | | |
| S-plus | single | | | | | |
| S-plus | batch | | | | | |

- Your multiplier (M over S), single and batch, beside the lecture's 15×:
- Whether S-plus's spend matched M's in fact, task by task:

**Slide 18's three questions**, for each kind of task.

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | | |
| Does spending more raise the score? | | |
| Given the same budget, did one agent do as well? | | |

- What you would have claimed from arms S and M alone, and what you claim now:

**Every arm M run that failed.**

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| | | | | |

## Part D · The decision

- One issue:
- A batch of five:
- The condition that would reopen it:
- The record: `decisions/0006-topology.md`

## AI assistance

Which tool, what it wrote, and what you checked:
