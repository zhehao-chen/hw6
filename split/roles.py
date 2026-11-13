"""The split's two roles, split by tool surface (Lecture 6, slide 11).

  investigator   issues_read, code_search, code_read_file, code_run_tests, and a local
                 return tool. It can read everything and write nothing.
  writer         issues_label, pulls_open, issues_comment, each scoped to its one issue,
                 every comment through with_disclosure. It can write and read nothing.

A role's surface is what its loop is handed: .schemas and .call(name, input). Any name
outside it is refused here, before the registry; every name inside it still goes
through the registry and the hook.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from harness.roles import arg, role_of, tool_for
from harness.schema import errors as schema_errors
from tools import ToolResult

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT / "contract.schema.json").read_text())
CONTRACT_FIELDS = ("result", "status", "searched", "not_searched", "calls_used", "could_not_determine")
RETURN_TOOL = "return_finding"

INVESTIGATOR_ROLES = ("read_issue", "search", "read_file", "run_tests")
WRITER_ROLES = ("apply_label", "open_pr", "comment")


def _local(content: str, is_error: bool = False) -> ToolResult:
    return ToolResult(content=content, is_error=is_error, latency_s=0.0)


class Surface:
    """The registry, cut down to one role's tools."""

    def __init__(self, tools, roles: tuple[str, ...]):
        self.tools = tools
        self.allowed = {tool_for(r) for r in roles}
        self._schemas = [s for s in tools.schemas if s["name"] in self.allowed]

    @property
    def schemas(self) -> list[dict]:
        return list(self._schemas)

    def refuse(self, name: str, why: str) -> ToolResult:
        return _local(f"refused: {why}", True)

    def call(self, name: str, args: dict, **kwargs) -> ToolResult:
        if name not in self.allowed:
            return self.refuse(name, f"{name} is not one of this role's tools ({', '.join(sorted(self.allowed))})")
        try:
            return self.tools.call(name, args, **kwargs)
        except Exception as exc:          # a raise ends the loop; report it to the model instead
            return _local(f"error: {type(exc).__name__}: {exc}"[:500], True)


# -- the investigator ---------------------------------------------------------------------------

def return_tool_schema() -> dict:
    """What the model fills in. searched and calls_used are not here: code fills them."""
    props = CONTRACT["properties"]
    return {
        "name": RETURN_TOOL,
        "strict": True,
        "description": ("Return your finding for the issue to the coordinator, once, when you are done. "
                        "The coordinator acts only on what this carries: it never sees your searches. "
                        "Your searches and reads are recorded by the harness; do not list them. "
                        "A return that breaks the contract is rejected with the reason; fix it and call again."),
        "input_schema": {
            "type": "object", "additionalProperties": False,
            "required": ["result", "status", "not_searched", "could_not_determine"],
            "properties": {
                "result": {**props["result"], "properties": {
                    "issue": {"type": "integer", "description": "The issue number you investigated."},
                    "label": {"type": "string", "enum": ["bug", "feature", "question", "docs"]},
                    "file": {"type": "string", "description": "The one file most responsible, as code_search prints its path, or none."},
                    "evidence": {"type": "string", "description": "One or two sentences: what in that file explains the issue."},
                    "pr_summary": {"type": "string", "description": "One or two sentences: what to change in the file. Empty when the file is none."},
                }},
                "status": {"type": "string", "enum": ["found", "candidate", "out_of_budget"],
                           "description": "found: you read the file and it explains the issue. candidate: your best guess, not confirmed. out_of_budget: you ran out of steps before you could decide."},
                "not_searched": {"type": "array", "items": {"type": "string"},
                                 "description": "Places or leads you know you did not look at; [] when none."},
                "could_not_determine": {"type": "array", "items": {"type": "string"},
                                        "description": "What you could not settle, each as one short sentence; [] when nothing."},
            },
        },
    }


class InvestigatorSurface(Surface):
    """Read tools, plus the return tool. Counts the worker's own registry calls and
    the queries and paths among them, so the return's facts are the run's facts."""

    def __init__(self, tools, issue: int, on_return):
        super().__init__(tools, INVESTIGATOR_ROLES)
        self.issue = issue
        self.on_return = on_return          # (contract, errors) -> None; records the worker_return line
        self.calls = 0
        self.searched: list[str] = []
        self.accepted: dict | None = None
        self.rejected = 0
        self._schemas.append(return_tool_schema())

    def _note(self, name: str, args: dict) -> None:
        role = role_of(name)
        if not role:
            return
        self.calls += 1                     # every tool_call line whose name is a role's, as the checker counts it
        value = None
        if role == "search":
            value = (args or {}).get(arg("search", "query"))
        elif role == "read_file":
            value = (args or {}).get(arg("read_file", "path"))
        if value is not None and str(value) not in self.searched:
            self.searched.append(str(value))

    def call(self, name: str, args: dict, **kwargs) -> ToolResult:
        if name == RETURN_TOOL:
            return self._return(args)
        if self.accepted is not None:
            return _local("refused: your finding was already returned; stop now.", True)
        self._note(name, args)
        return super().call(name, args, **kwargs)

    def _return(self, args) -> ToolResult:
        if self.accepted is not None:
            return _local("refused: your finding was already returned; stop now.", True)
        given = args if isinstance(args, dict) else {"_raw": args}
        # The facts come from this worker's own calls; what the model sent is never repaired.
        contract = {k: v for k, v in given.items() if k not in ("searched", "calls_used")}
        contract["searched"] = list(self.searched)
        contract["calls_used"] = self.calls
        errs = schema_errors(contract, CONTRACT)
        self.on_return(contract, errs)
        if errs:
            self.rejected += 1
            return _local("rejected: the return breaks the contract, and nothing was acted on: "
                          + "; ".join(errs[:5]) + ". Call return_finding again with every field in its shape.", True)
        self.accepted = contract
        return _local("accepted. Your work is done: stop now, with no further tool calls.")


# -- the writer ---------------------------------------------------------------------------------

class WriterSurface(Surface):
    """The three writes, each for this writer's one issue only."""

    def __init__(self, tools, issue: int):
        super().__init__(tools, WRITER_ROLES)
        self.issue = int(issue)
        self.number_arg = {tool_for(r): arg(r, "number") for r in WRITER_ROLES}

    def call(self, name: str, args: dict, **kwargs) -> ToolResult:
        if name in self.number_arg and isinstance(args, dict):
            given = args.get(self.number_arg[name])
            digits = re.findall(r"\d+", str(given))
            same = len(digits) == 1 and int(digits[0]) == self.issue
            if not same:
                return self.refuse(name, f"this writer writes to issue {self.issue} only, not {given!r}")
        return super().call(name, args, **kwargs)


__all__ = ["Surface", "InvestigatorSurface", "WriterSurface", "return_tool_schema", "CONTRACT",
           "CONTRACT_FIELDS", "RETURN_TOOL"]
