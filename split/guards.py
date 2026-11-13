"""The guards the replays call (checks/FORMATS.md, section 14.6), and the split uses live.

  WaitGraph      deadlock detection: every wait on another agent is an edge; a wait
                 that closes a cycle is returned, and one worker in it is stopped.
  SharedState    compare-and-set over the state agents share: a write names the
                 version it read and is refused if the state has moved since.
  check_combined the combined result, read from the tracker's end state, against rules
                 set before the run. It needs no answer key.
"""

from __future__ import annotations

import threading
from pathlib import PurePosixPath

from harness.formats import normalize_path, parse_triage_comment

COORDINATOR = "coordinator"


class WaitGraph:
    """Who waits on whom. Edges are added by wait() and removed by release()."""

    def __init__(self, coordinator: str = COORDINATOR):
        self.coordinator = coordinator
        self.edges: dict[str, dict[str, str]] = {}      # waiter -> {on: what}
        self._lock = threading.Lock()

    def wait(self, waiter: str, on: str, what: str = "") -> list[str] | None:
        """Record that `waiter` now waits on `on`. The cycle this wait closes, as the
        agents in it in wait order (waiter first), or None."""
        with self._lock:
            self.edges.setdefault(waiter, {})[on] = what
            path = self._path(on, waiter)
            return [waiter] + path[:-1] if path else None

    def release(self, waiter: str, on: str) -> None:
        """`waiter` got what it waited on from `on`: the edge goes."""
        with self._lock:
            self.edges.get(waiter, {}).pop(on, None)

    def remove(self, agent: str) -> None:
        """A stopped or finished agent: no one waits on it, and it waits on no one."""
        with self._lock:
            self.edges.pop(agent, None)
            for targets in self.edges.values():
                targets.pop(agent, None)

    def victim(self, cycle: list[str]) -> str:
        """The worker to stop: never the coordinator; of the rest, the one whose wait
        closed the cycle (the cycle's first agent), so the agent that waited longest
        keeps its work."""
        workers = [a for a in cycle if a != self.coordinator]
        if not workers:
            raise ValueError("a cycle of the coordinator alone has no worker to stop")
        return workers[0]

    def _path(self, start: str, goal: str) -> list[str] | None:
        """A path of waits from start to goal, as the agents after start, ending with goal."""
        stack = [(start, [start])]
        seen = set()
        while stack:
            node, path = stack.pop()
            if node == goal:
                return path
            if node in seen:
                continue
            seen.add(node)
            for nxt in self.edges.get(node, {}):
                stack.append((nxt, path + [nxt]))
        return None


class SharedState:
    """Versioned shared state, path -> content, written only by compare-and-set."""

    def __init__(self, initial: dict[str, str] | None = None):
        self._content: dict[str, str] = dict(initial or {})
        self._version: dict[str, int] = {p: 1 for p in self._content}
        self.refused: list[dict] = []
        self._lock = threading.Lock()

    def read(self, agent: str, path: str) -> tuple[str, int]:
        """The content and its version (0 for a path never written)."""
        with self._lock:
            return self._content.get(path, ""), self._version.get(path, 0)

    def write(self, agent: str, path: str, content: str, version: int) -> bool:
        """Compare-and-set: write only if `path` is still at `version`. True when
        written; False when refused, leaving the content as it was."""
        with self._lock:
            current = self._version.get(path, 0)
            if current != version:
                self.refused.append({"agent": agent, "path": path, "read_version": version, "current": current})
                return False
            self._content[path] = content
            self._version[path] = current + 1
            return True

    def content(self, path: str) -> str:
        with self._lock:
            return self._content.get(path, "")


def _names(text: str, file: str) -> bool:
    text = (text or "").lower()
    return file.lower() in text or PurePosixPath(file).name.lower() in text


def check_combined(task, state: dict) -> list[str]:
    """The combined result's violations of the task's rules; [] when it passes.

    The rules, set before any run, for each of the task's issues: exactly one comment,
    with a label line and a file line; exactly that label on the issue; one pull request
    naming the comment's file when it is not none, and none when it is. No answer key."""
    issues = task.issues if hasattr(task, "issues") else task["issues"]
    out: list[str] = []
    for n in issues:
        n = int(n)
        entry = state.get(n, state.get(str(n))) or {}
        comments = list(entry.get("comments") or [])
        labels = sorted({str(l).strip().lower() for l in entry.get("labels") or []})
        prs = list(entry.get("prs") or [])
        if len(comments) != 1:
            out.append(f"#{n}: {len(comments)} comments, not one")
            continue
        label, file = parse_triage_comment(comments[0])
        file = normalize_path(file) if file else file
        if not label or not file:
            out.append(f"#{n}: the comment lacks a {'label' if not label else 'file'} line")
            continue
        if labels != [label]:
            out.append(f"#{n}: labels on the issue {labels}, where the comment says {label!r}")
        if file == "none":
            if prs:
                out.append(f"#{n}: {len(prs)} pull requests, where the comment's file is none")
        elif len(prs) != 1:
            out.append(f"#{n}: {len(prs)} pull requests, where the comment names {file}")
        elif not _names(f"{prs[0].get('title', '')}\n{prs[0].get('body', '')}", file):
            out.append(f"#{n}: the pull request does not name {file}, the comment's file")
    return out


__all__ = ["WaitGraph", "SharedState", "check_combined", "COORDINATOR"]
