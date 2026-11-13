"""Assignment 6, Part C: every finished measured run's outcome, from the tracker.

    python eval/results_06.py              # writes results/runs_06.jsonl, prints the summary
    python eval/results_06.py --json       # the summary as reports/LAB_06.json's arms, multiplier and constants

One line per finished run (a real backend, on a fixtures/tasks6 task; checks/FORMATS.md,
section 14.7). passed and parts come from eval/check_task.py's grounded check of the
tracker; tokens from run_end.totals.total_tokens; wall_s from run_end.elapsed_s. Nothing
is read from any agent's words.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.check_task import check_task            # noqa: E402
from harness.runner import is_free                 # noqa: E402
from harness.tasks import load_tasks               # noqa: E402

ARMS = {"agent": "S", "split": "M", "splus": "S_plus"}
SWEEPS = 3


class Tracker:
    """The three reads check_task makes, over the tracker's database and its archives."""

    def __init__(self, root: Path = ROOT):
        self.rows = {t: {} for t in ("comments", "prs", "labels")}
        dbs = [root / "tracker" / "tracker.db", *sorted((root / "tracker" / "archive").glob("*.db"))]
        for path in [p for p in dbs if p.exists()]:
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            try:
                for table in self.rows:
                    try:
                        for row in db.execute(f"SELECT * FROM {table} ORDER BY id"):
                            self.rows[table].setdefault(row["run_id"], []).append(dict(row))
                    except sqlite3.OperationalError:
                        pass
            finally:
                db.close()

    def comments(self, run_id, issue=None):
        return [r for r in self.rows["comments"].get(run_id, []) if issue is None or int(r["issue"]) == int(issue)]

    def labels(self, run_id, issue=None, active=True):
        return [r for r in self.rows["labels"].get(run_id, [])
                if (issue is None or int(r["issue"]) == int(issue)) and (not active or r.get("removed_at") is None)]

    def prs(self, run_id, branch=None, state="open"):
        return [r for r in self.rows["prs"].get(run_id, [])
                if (branch is None or r["branch"] == branch) and (state is None or r.get("state") == state)]


def finished_runs(tasks: dict) -> list[tuple[dict, dict]]:
    """(run_start, run_end) for every finished run of an arm on the task set, on a real backend."""
    out = []
    for path in sorted((ROOT / "runs").glob("*.jsonl")):
        lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        if not lines or lines[0].get("type") != "run_start":
            continue
        start = lines[0]
        if start.get("lab") != "06" or start.get("task") not in tasks or start.get("way") not in ARMS:
            continue
        if is_free(start.get("backend") or ""):
            continue
        end = lines[-1] if lines[-1].get("type") == "run_end" else None
        reasons = {r.get("terminal_reason") for r in lines if r.get("type") == "end"}
        if end is None or reasons & {"quota", "rate_limited"}:
            continue
        out.append((start, end))
    return out


def rows(tasks: dict) -> list[dict]:
    tracker = Tracker()
    out = []
    for start, end in finished_runs(tasks):
        run_id = start["run_id"]
        checked = check_task(run_id, tasks[start["task"]], tracker=tracker)
        out.append({"run_id": run_id, "arm": ARMS[start["way"]], "way": start["way"], "task": start["task"],
                    "kind": start["kind"], "sweep": start.get("sweep"), "passed": checked["passed"],
                    "parts": {str(k): v for k, v in checked["parts"].items()},
                    "tokens": int((end.get("totals") or {}).get("total_tokens") or 0),
                    "wall_s": float(end.get("elapsed_s") or 0.0),
                    "budget": start.get("budget"), "ceiling": start.get("ceiling"),
                    "started_at": start.get("started_at"), "constants": start.get("constants")})
    return out


def mean(values):
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def summarize(rs: list[dict]) -> dict:
    out = {}
    for kind in ("single", "batch"):
        mine = [r for r in rs if r["kind"] == kind]
        per_task, sweeps = {}, {}
        for r in mine:
            per_task[r["task"]] = per_task.get(r["task"], 0) + int(r["passed"])
            sweeps[r["sweep"]] = sweeps.get(r["sweep"], 0) + int(r["passed"])
        out[kind] = {"runs": len(mine), "passes": sum(int(r["passed"]) for r in mine),
                     "per_task": dict(sorted(per_task.items())),
                     "sweep_min": min(sweeps.values()) if sweeps else None,
                     "sweep_max": max(sweeps.values()) if sweeps else None,
                     "all_three": sum(1 for v in per_task.values() if v >= SWEEPS),
                     "mean_tokens": round(mean(r["tokens"] for r in mine)) if mine else None,
                     "mean_wall_s": round(mean(r["wall_s"] for r in mine), 1) if mine else None}
    return out


def report(rs: list[dict]) -> dict:
    arms = {arm: summarize([r for r in rs if r["arm"] == arm]) for arm in ("S", "M", "S_plus")}
    mult = {k: (round(arms["M"][k]["mean_tokens"] / arms["S"][k]["mean_tokens"], 2)
                if arms["M"][k]["mean_tokens"] and arms["S"][k]["mean_tokens"] else None) for k in ("single", "batch")}
    consts = {json.dumps(r["constants"], sort_keys=True) for r in rs}
    per_task = {}
    for t in sorted({r["task"] for r in rs}):
        row = {}
        for arm in ("S", "M", "S_plus"):
            mine = [r for r in rs if r["task"] == t and r["arm"] == arm]
            row[arm] = {"passes": sum(r["passed"] for r in mine), "runs": len(mine),
                        "mean_tokens": round(mean(r["tokens"] for r in mine)) if mine else None,
                        "mean_wall_s": round(mean(r["wall_s"] for r in mine), 1) if mine else None,
                        "budgets": sorted({r["budget"] for r in mine}, key=str)}
            row[arm]["issue_passes"] = {}
            for r in mine:
                for k, v in r["parts"].items():
                    row[arm]["issue_passes"][k] = row[arm]["issue_passes"].get(k, 0) + int(v)
        per_task[t] = row
    return {"constants": json.loads(next(iter(consts))) if len(consts) == 1 else sorted(consts),
            "arms": arms, "multiplier": mult, "per_task": per_task}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="fixtures/tasks6")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args(argv)
    tasks = {t.id: t for t in load_tasks(args.tasks)}
    rs = rows(tasks)
    out = ROOT / "results" / "runs_06.jsonl"
    out.parent.mkdir(exist_ok=True)
    keep = ("run_id", "arm", "way", "task", "kind", "sweep", "passed", "parts", "tokens", "wall_s")
    out.write_text("".join(json.dumps({k: r[k] for k in keep}) + "\n" for r in rs))
    summary = report(rs)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 0
    print(f"{len(rs)} finished runs -> {out.relative_to(ROOT)}")
    for arm, kinds in summary["arms"].items():
        for kind, s in kinds.items():
            print(f"{arm:7} {kind:6} {s['passes']}/{s['runs']} sweeps {s['sweep_min']}-{s['sweep_max']} "
                  f"all3 {s['all_three']} tokens {s['mean_tokens']} wall {s['mean_wall_s']}s")
    print("multiplier", summary["multiplier"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
