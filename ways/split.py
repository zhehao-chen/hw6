"""Arm M: the split. A coordinator in code, and per issue two roles split by tool surface.

  coordinator    code, not a model: hands out issues, validates every return against
                 split/contract.schema.json, dispatches writers, and checks the end state.
  investigator   one per issue (split/roles.py): reads only; returns the contract.
  writer         one per issue: label, draft PR, comment; that issue only.

On a batch, the five investigators run at once, then the five writers. The five checks
(slide 47), and where each is:
  1. the return contract    split/roles.py InvestigatorSurface._return, on every return
  2. deadlock detection     split/guards.py WaitGraph: every wait goes through it and the trace
  3. the combined result    split/guards.py check_combined, on the tracker's end state, last
  4. compare-and-set        split/guards.py SharedState: the findings board the writers read;
                            the tracker's writes keep their idempotency keys (Assignment 3)
  5. one trace              every line through ctx.agent(...): agent, parent, tokens

The budget: ctx.budget is the whole run's, shared by every agent. Each issue gets
budget / n; of that, the investigator may spend 60%, the writer 20%, and 20% is held
back for one re-investigation when an investigator ends without a valid return.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from agent.loop import load_bounds, run_loop
from harness.tasks import end_state
from split.guards import COORDINATOR, SharedState, WaitGraph, check_combined
from split.roles import InvestigatorSurface, WriterSurface
from ways.agent import Disclosing, disclosure_line

INVESTIGATOR_SHARE, WRITER_SHARE = 0.60, 0.20          # of each issue's share; the rest is held back
INVESTIGATOR_STEPS, WRITER_STEPS = 10, 5


class Coordinator:
    def __init__(self, ctx):
        self.ctx = ctx
        self.lead = ctx.agent(COORDINATOR)
        self.graph = WaitGraph(COORDINATOR)
        self.board = SharedState({})                    # finding/<issue> -> the accepted contract, as JSON
        self.issues = list(ctx.issues)
        budget = ctx.budget or load_bounds().max_tokens * len(self.issues)
        self.per_issue = budget // len(self.issues)
        self.base = load_bounds()
        self._lock = threading.Lock()

    # -- waits ----------------------------------------------------------------------------------
    def wait(self, on: str, what: str, turn: int) -> None:
        self.lead.trace.event("wait", waiter=COORDINATOR, on=on, what=what, turn=turn)
        cycle = self.graph.wait(COORDINATOR, on, what)
        if cycle:
            victim = self.graph.victim(cycle)
            self.lead.trace.event("worker_stopped", worker=victim, reason=f"cycle of waits: {' -> '.join(cycle)}")
            self.graph.remove(victim)

    def done(self, on: str) -> None:
        self.graph.release(COORDINATOR, on)

    # -- the investigator -------------------------------------------------------------------------
    def investigate(self, issue: int, attempt: int, share: int) -> dict | None:
        wid = f"investigator-{issue}" + (f"-r{attempt}" if attempt > 1 else "")
        worker = self.ctx.agent(wid, parent=COORDINATOR)

        def on_return(contract, errs):
            self.lead.trace.event("worker_return", worker=wid, contract=contract, valid=not errs, errors=errs)

        surface = InvestigatorSurface(self.ctx.tools, issue, on_return)
        bounds = replace(self.base, max_steps=INVESTIGATOR_STEPS, max_tokens=share)
        self.wait(wid, "a finding", turn=attempt - 1)
        try:
            run_loop(worker.client, surface, self.ctx.prompt("investigator.md"),
                     f"Investigate issue #{issue}, and return your finding.", bounds, worker.trace)
        finally:
            self.done(wid)
        found = surface.accepted
        if found is None:
            return None
        key = f"finding/{issue}"
        _, version = self.board.read(COORDINATOR, key)
        if not self.board.write(COORDINATOR, key, json.dumps(found), version):
            self.lead.trace.event("cas_refused", worker=wid, path=key, version=version)
            return None
        return found

    def find(self, issue: int) -> dict | None:
        found = self.investigate(issue, 1, int(self.per_issue * INVESTIGATOR_SHARE))
        if found is None:
            spent = self.ctx.agent(f"investigator-{issue}", parent=COORDINATOR).client.total_tokens
            held = int(self.per_issue * (1 - WRITER_SHARE)) - spent
            if held > self.per_issue * 0.1:
                self.lead.trace.event("reinvestigate", issue=issue, reason="no valid return", share=held)
                found = self.investigate(issue, 2, held)
        return found

    # -- the writer -----------------------------------------------------------------------------
    def write(self, issue: int) -> None:
        text, _ = self.board.read(f"writer-{issue}", f"finding/{issue}")
        if not text:
            self.lead.trace.event("no_finding", issue=issue, reason="no valid return; nothing is written")
            return
        found = json.loads(text)
        r = found["result"]
        brief = (f"Write the triage for issue #{issue}.\n"
                 f"label: {r['label']}\n"
                 f"file: {r['file']}\n"
                 f"Evidence: {r['evidence']}\n"
                 f"What to change: {r['pr_summary'] or '(nothing: no pull request)'}\n"
                 f"Investigator's status: {found['status']}"
                 + (f"; could not determine: {'; '.join(found['could_not_determine'])}"
                    if found["could_not_determine"] else ""))
        wid = f"writer-{issue}"
        worker = self.ctx.agent(wid, parent=COORDINATOR)
        surface = Disclosing(WriterSurface(self.ctx.tools, issue), disclosure_line())
        bounds = replace(self.base, max_steps=WRITER_STEPS, max_tokens=int(self.per_issue * WRITER_SHARE))
        self.wait(wid, "the label, pull request and comment", turn=1)
        try:
            run_loop(worker.client, surface, self.ctx.prompt("writer.md"), brief, bounds, worker.trace)
        finally:
            self.done(wid)

    # -- the run --------------------------------------------------------------------------------
    def run(self) -> None:
        n = len(self.issues)
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(self.find, self.issues))
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(self.write, self.issues))
        task = self.ctx.task
        if task is not None:
            violations = check_combined(task, end_state(self.ctx.tracker, self.ctx.run_id, task))
            self.lead.trace.event("combined_check", passed=not violations, violations=violations)
        tokens = {a.id: a.client.total_tokens for a in self.ctx.agents.values()}
        self.lead.trace.event("agent_tokens", tokens=tokens, total=sum(tokens.values()))


def run(ctx) -> None:
    Coordinator(ctx).run()


__all__ = ["run", "Coordinator"]
