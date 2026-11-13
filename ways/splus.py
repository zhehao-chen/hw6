"""Arm S-plus: one agent given what arm M actually spent (slide 16's fair rival).

run.py --match split sets ctx.budget to arm M's mean spend on this task. One agent has
nowhere to put that many tokens in one context, so it spends them on further attempts,
one after another, each a fresh context with read-only tools; then it chooses an answer
by a vote over its attempts (no answer key), and writes only that answer, once: the
label, a draft PR when the file is not none, and the comment last, with the disclosure
line added in code. Nothing runs at once, and there are no roles: the attempts are the
same loop, the same prompt and the same tools, repeated.

The agent is `splus` (parent none); each attempt's loop needs a trace of its own, so each
is `attempt-<k>-<issue>`, its child.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from agent.loop import load_bounds, run_loop
from harness.formats import normalize_path
from harness.roles import arg, tool_for
from split.roles import Surface
from tools import ToolResult
from ways.agent import disclosure_line, with_disclosure

ROOT_AGENT = "splus"
READS = ("read_issue", "search", "read_file", "run_tests")
ATTEMPT_STEPS = 10
MAX_ATTEMPTS = 15
SUBMIT = "submit_answer"


def submit_schema() -> dict:
    return {"name": SUBMIT, "strict": True,
            "description": "Submit this attempt's answer for the issue, once, when you are done. Then stop.",
            "input_schema": {"type": "object", "additionalProperties": False,
                             "required": ["label", "file", "summary"],
                             "properties": {
                                 "label": {"type": "string", "enum": ["bug", "feature", "question", "docs"]},
                                 "file": {"type": "string", "description": "The file's path as the search printed it, or none."},
                                 "summary": {"type": "string", "description": "One or two sentences: what to change in that file."}}}}


class AttemptSurface(Surface):
    def __init__(self, tools):
        super().__init__(tools, READS)
        self._schemas.append(submit_schema())
        self.answer: dict | None = None

    def call(self, name, args, **kwargs):
        if name == SUBMIT:
            if self.answer is not None:
                return ToolResult("refused: already submitted; stop now.", True, 0.0)
            label = str((args or {}).get("label", "")).strip().lower()
            file = normalize_path(str((args or {}).get("file", "")).strip()) or "none"
            if label not in ("bug", "feature", "question", "docs"):
                return ToolResult("rejected: label is one of bug, feature, question, docs.", True, 0.0)
            self.answer = {"label": label, "file": file, "summary": str((args or {}).get("summary", ""))}
            return ToolResult("submitted. Stop now, with no further tool calls.", False, 0.0)
        if self.answer is not None:
            return ToolResult("refused: already submitted; stop now.", True, 0.0)
        return super().call(name, args, **kwargs)


def vote(answers: list[dict]) -> dict | None:
    """The (label, file) most attempts gave; ties go to the one given first."""
    if not answers:
        return None
    counts = Counter((a["label"], a["file"]) for a in answers)
    best = max(counts.values())
    winner = next((a["label"], a["file"]) for a in answers if counts[(a["label"], a["file"])] == best)
    return next(a for a in answers if (a["label"], a["file"]) == winner) | {"votes": best, "of": len(answers)}


def triage(ctx, me, issue: int, share: int, base) -> None:
    answers, spent, k = [], 0, 0
    while k < MAX_ATTEMPTS:
        k += 1
        attempt = ctx.agent(f"attempt-{k}-{issue}", parent=ROOT_AGENT)
        surface = AttemptSurface(ctx.tools)
        remaining = max(share - spent, 1)
        run_loop(attempt.client, surface, ctx.prompt("splus_attempt.md"),
                 f"Triage issue #{issue}: find its label and the file responsible.",
                 replace(base, max_steps=ATTEMPT_STEPS, max_tokens=remaining), attempt.trace)
        spent += attempt.client.total_tokens
        if surface.answer:
            answers.append(surface.answer)
        per_attempt = spent / k
        # Stop when another attempt would, on average, carry the issue past its share.
        if spent + per_attempt / 2 > share:
            break
    chosen = vote(answers)
    me.trace.event("vote", issue=issue, attempts=k, answers=[(a["label"], a["file"]) for a in answers],
                   chosen=None if chosen is None else [chosen["label"], chosen["file"]],
                   votes=None if chosen is None else chosen["votes"], spent=spent, share=share)
    if chosen is None:
        return
    write(me, issue, chosen)


def write(me, issue: int, chosen: dict) -> None:
    """The chosen answer, written once by code: label, PR when there is a file, comment last."""
    name = f"issue-{issue}"
    label, file, summary = chosen["label"], chosen["file"], chosen["summary"].strip()
    me.call_tool(0, tool_for("apply_label"), {arg("apply_label", "number"): name, arg("apply_label", "label"): label})
    if file != "none":
        me.call_tool(0, tool_for("open_pr"), {
            arg("open_pr", "number"): name, arg("open_pr", "branch"): f"repomind/issue-{issue}",
            arg("open_pr", "title"): f"Fix issue {issue} in {file}"[:120],
            arg("open_pr", "body"): f"File: {file}\n\n{summary or 'Change the code there.'}"})
    note = summary or "See the label and file above."
    body = with_disclosure(f"label: {label}\nfile: {file}\n\n{note}"[:1800], disclosure_line())
    me.call_tool(0, tool_for("comment"), {arg("comment", "number"): name, arg("comment", "body"): body})


def run(ctx) -> None:
    me = ctx.agent(ROOT_AGENT)
    issues = list(ctx.issues)
    base = load_bounds()
    budget = ctx.budget or base.max_tokens * len(issues)
    share = int(budget // len(issues))
    for issue in issues:                      # one after another: nothing runs at once
        triage(ctx, me, issue, share, base)


__all__ = ["run", "vote"]
