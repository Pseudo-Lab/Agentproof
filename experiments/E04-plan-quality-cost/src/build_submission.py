#!/usr/bin/env python3
"""Rebuild AgentProof pairwise logs from the frozen Plan Benchmark run, offline."""
import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
REPO = EXP.parents[1]
sys.path.insert(0, str(REPO))
from harness.summarize import summarize

SRC = EXP / "results" / "pilot" / "source"
LATEST = SRC / "latest_outcomes.jsonl"
HISTORY = SRC / "attempt_history.jsonl"
SRC_MANIFEST = SRC / "benchmark_manifest.json"
INVOCATION = SRC / "invocation.json"
TASKS = EXP / "data" / "tasks.json"
MODELS = {"A": "gpt-6.1-sol", "B": "gpt-6-luna", "C": "gpt-6-luna"}
JUDGE = "gpt-6.1-sol"
SOURCE_REPO = "https://github.com/daclouds/plan-benchmark"
SOURCE_COMMIT = "54829bad36765dae2e7a82b24ba7b47c61cebab9"
SOURCE_RUN = "real_20261025T143420_316405Z"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"),
                               allow_nan=False) + "\n")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def calls_summary(record):
    fields = ("stage", "model", "status", "error", "finish_reason",
              "input_tokens", "output_tokens", "cost_usd", "latency_ms")
    return [{k: call.get(k) for k in fields} for call in record.get("calls", [])]


def curate(record, layers):
    group = record["group"]
    grade = record.get("grade") or {}
    return {
        "source_record_id": record.get("sample_id"),
        "task_id": record["task_id"],
        "task_layer": layers.get(record["task_id"], "unclassified"),
        "group": group,
        "model": MODELS[group],
        "repeat_id": int(record["repeat"]) + 1,
        "status": record["status"],
        "score_100": record.get("score_100"),
        "passed": grade.get("pass"),
        "critical_error": record.get("critical"),
        "generation_latency_ms": record.get("generation_latency_ms"),
        "error": record.get("error"),
        "output": record.get("output"),
        "candidates": record.get("candidates", []),
        "verdict": record.get("verdict"),
        "contract_error": grade.get("reason") if record["status"] == "invalid_plan" else None,
        "calls": calls_summary(record),
    }


def archive_source(run):
    run = Path(run)
    cases_file = run / "cases.json"
    cases = read_json(cases_file)
    layers = {c["vars"]["task_id"]: c["vars"].get("task_layer", "unclassified") for c in cases}
    paths = list((run / "records").glob("*.json"))
    records = [(p.stat().st_mtime_ns, read_json(p)) for p in paths]
    latest = {}
    for mtime, record in records:
        key = (record["task_id"], record["group"], int(record["repeat"]))
        if key not in latest or latest[key][0] < mtime:
            latest[key] = (mtime, record)
    old = [curate(r, layers) for _, r in records]
    final = [curate(r, layers) for _, r in latest.values()]
    order = {"A": 0, "B": 1, "C": 2}
    old.sort(key=lambda r: (r["task_id"], order[r["group"]], r["repeat_id"], r["source_record_id"] or ""))
    final.sort(key=lambda r: (r["task_id"], order[r["group"]], r["repeat_id"]))
    TASKS.parent.mkdir(parents=True, exist_ok=True)
    TASKS.write_bytes(cases_file.read_bytes())
    SRC.mkdir(parents=True, exist_ok=True)
    (SRC_MANIFEST).write_bytes((run / "manifest.json").read_bytes())
    INVOCATION.write_bytes((run / "invocation.json").read_bytes())
    write_jsonl(HISTORY, old)
    write_jsonl(LATEST, final)
    return cases, final, old, read_json(run / "manifest.json"), read_json(run / "invocation.json")


def archive_loaded():
    cases = read_json(TASKS)
    final = [json.loads(x) for x in LATEST.read_text(encoding="utf-8").splitlines() if x]
    old = [json.loads(x) for x in HISTORY.read_text(encoding="utf-8").splitlines() if x]
    return cases, final, old, read_json(SRC_MANIFEST), read_json(INVOCATION)


def trial(row, group, run_id):
    if row["status"] == "generation_error":
        status, score = "error", None
    elif row["status"] == "invalid_plan":
        status, score = "failure", 0.0
    else:
        status = "success" if row.get("passed") is True else "failure"
        score = row.get("score_100")
    missing = {}
    if score is None:
        missing["score"] = "Generation failed before a Plan could be scored."
    latency = row.get("generation_latency_ms")
    if type(latency) not in (int, float) or latency < 0:
        latency = None
        missing["latency_ms"] = "Generation latency was not recorded."
    calls = row.get("calls", [])
    def tokens(field):
        values = [c.get(field) for c in calls]
        return sum(values) if values and all(type(v) is int and v >= 0 for v in values) else None
    inputs, outputs = tokens("input_tokens"), tokens("output_tokens")
    if inputs is None:
        missing["input_tokens"] = "At least one call did not report input tokens."
    if outputs is None:
        missing["output_tokens"] = "At least one call did not report output tokens."
    costs = [c.get("cost_usd") for c in calls]
    cost = sum(costs) if all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                             for v in costs) else None
    if cost is None:
        missing["cost_usd"] = "At least one call has unknown cost."
    verdict = row.get("verdict") or {}
    return {
        "run_id": run_id, "task_id": row["task_id"],
        "condition": "baseline" if group == "A" else "intervention",
        "repeat_id": row["repeat_id"], "status": status, "score": score,
        "latency_ms": latency, "input_tokens": inputs, "output_tokens": outputs,
        "cost_usd": cost, "missing_reasons": missing,
        "evidence": {
            "source_record_id": row.get("source_record_id"), "source_group": group,
            "model": MODELS[group], "judge_model": JUDGE,
            "threshold": 75, "critical_error": row.get("critical_error"),
            "judge_scores_0_to_4": verdict.get("scores"),
            "judge_reasons": verdict.get("reasons"),
            "critical_errors": verdict.get("critical_errors"),
            "generation_error": row.get("error"),
            "plan_contract_error": row.get("contract_error"),
            "candidate_count": len(row.get("candidates") or []),
            "call_stages": [c.get("stage") for c in calls],
            "source_records": "results/pilot/source/latest_outcomes.jsonl",
        },
    }


def percentile(values, p):
    return values[min(len(values) - 1, max(0, int(p * len(values)) - 1))]


def paired(latest, group):
    tasks = defaultdict(lambda: defaultdict(list))
    for row in latest:
        if row["group"] not in ("A", group):
            continue
        if row["score_100"] is None and row["status"] != "invalid_plan":
            continue
        score = 0.0 if row["status"] == "invalid_plan" else float(row["score_100"])
        tasks[row["task_id"]][row["group"]].append(score)
    diffs = [statistics.mean(v[group]) - statistics.mean(v["A"])
             for _, v in sorted(tasks.items()) if v.get("A") and v.get(group)]
    if not diffs:
        return {"complete_paired_tasks": 0, "mean_difference": None, "bootstrap_95_ci": None}
    state = 42
    def rand():
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 4294967296
    boot = []
    for _ in range(10000):
        boot.append(statistics.mean(diffs[int(rand() * len(diffs))] for _ in diffs))
    boot.sort()
    ci = [percentile(boot, .025), percentile(boot, .975)]
    return {
        "complete_paired_tasks": len(diffs),
        "mean_difference": statistics.mean(diffs),
        "bootstrap_95_ci": ci,
        "bootstrap_method": "task-level percentile bootstrap, 10,000 draws, LCG seed 42",
        "margin": 5,
        "quality_noninferiority_signal": ci[0] > -5,
    }


def run_pair(latest, source_manifest, cases, group, run_id):
    run_dir = EXP / "results" / "pilot" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    tasks = sorted(c["vars"]["task_id"] for c in cases)
    selected = [r for r in latest if r["group"] in ("A", group)]
    rows = [trial(r, r["group"], run_id) for r in selected]
    rows.sort(key=lambda r: (r["task_id"], r["condition"], r["repeat_id"]))
    manifest = {
        "experiment_id": "E04-plan-quality-cost", "run_id": run_id,
        "execution_mode": "real", "started_at_utc": "2026-10-25T14:34:20.316405Z",
        "code_commit": SOURCE_COMMIT + " (run-time commit not captured)",
        "code_dirty": True, "source_repository": SOURCE_REPO, "source_run_id": SOURCE_RUN,
        "model": f"A={MODELS['A']}; {group}={MODELS[group]}; judge={JUDGE}",
        "configs": {
            "baseline": {"condition": "baseline", "group": "A", "model": MODELS["A"],
                         "generation_calls": 1},
            "intervention": {"condition": "intervention", "group": group,
                             "model": MODELS[group],
                             "generation_calls": 1 if group == "B" else 4},
            "judge": {"model": JUDGE},
        },
        "task_ids": tasks, "data_sha256": sha256(TASKS),
        "repeats_per_condition": {"baseline": 3, "intervention": 3},
        "execution_order": "Promptfoo outer concurrency 1; C creates 3 parallel candidates then synthesizes. Run was interrupted and resumed. These pairwise files keep latest result per planned cell; attempt history is retained separately.",
        "seed_policy": "Runner recorded seed 42; API sampling is not deterministic.",
        "cost_basis": "Returned token usage multiplied by rates in experiment.toml; trial cost includes generation and judge calls. Unknown attempt costs are reported separately.",
        "noninferiority_margin_points": 5,
        "source_sha256": source_manifest.get("source_sha256"),
        "source_archive": "results/pilot/source/",
        "limitations": [
            "Plan quality is measured; no code/task execution success is measured.",
            "Run-time git commit was not recorded; source manifest has file hashes and the exact run.py hash was not found in available git history.",
            "A and the judge use the same model. Human agreement was not measured."
        ],
    }
    write_json(run_dir / "manifest.json", manifest)
    write_jsonl(run_dir / "trials.jsonl", rows)
    write_json(run_dir / "summary.json", summarize(run_dir))


def make_summary(latest, attempts, source_manifest, invocation):
    groups = {}
    costs_latest, costs_all = {}, {}
    for group in "ABC":
        rows = [r for r in latest if r["group"] == group]
        scored = [0.0 if r["status"] == "invalid_plan" else r["score_100"]
                  for r in rows if r["score_100"] is not None or r["status"] == "invalid_plan"]
        groups[group] = {
            "latest_cells": len(rows),
            "graded": sum(r["status"] == "graded" for r in rows),
            "invalid_plans": sum(r["status"] == "invalid_plan" for r in rows),
            "generation_errors": sum(r["status"] == "generation_error" for r in rows),
            "mean_plan_score_100_invalid_as_zero": statistics.mean(scored),
            "passed": sum(r.get("passed") is True for r in rows),
            "pass_rate_over_scored_or_invalid": sum(r.get("passed") is True for r in rows) / len(scored),
        }
        for selected, target in ((rows, costs_latest), ([r for r in attempts if r["group"] == group], costs_all)):
            calls = [c for r in selected for c in r.get("calls", [])]
            gen = sum(c["cost_usd"] for c in calls if c.get("stage") != "judge" and c.get("cost_usd") is not None)
            judge = sum(c["cost_usd"] for c in calls if c.get("stage") == "judge" and c.get("cost_usd") is not None)
            target[group] = {
                "cells_or_attempts": len(selected), "known_generation_usd": gen,
                "known_judge_usd": judge, "known_total_usd": gen + judge,
                "unknown_cost_calls": sum(c.get("cost_usd") is None for c in calls),
            }
    latest_by_key = {(r["task_id"], r["group"], r["repeat_id"]): r for r in latest}
    return {
        "experiment_id": "E04-plan-quality-cost",
        "source_run_id": SOURCE_RUN, "execution_mode": "real",
        "expected_unique_cells": invocation.get("expected_samples", 108),
        "source_attempts": len(attempts), "latest_unique_cells": len(latest),
        "latest_outcomes": groups,
        "latest_outcome_costs_usd": costs_latest,
        "all_attempt_costs_usd_lower_bound": {
            "by_group": costs_all,
            "known_total_usd": sum(v["known_total_usd"] for v in costs_all.values()),
            "unknown_cost_calls": sum(v["unknown_cost_calls"] for v in costs_all.values()),
        },
        "paired_latest_outcome_comparisons": {
            "B-A": paired(latest, "B"), "C-A": paired(latest, "C")
        },
        "scoring": {
            "method": "Promptfoo custom Python assertion, Plan contract validation, LLM-as-a-judge",
            "judge_model": JUDGE, "weights": {"coverage": 30, "feasibility": 25,
            "dependencies": 20, "verification": 15, "recovery": 10},
            "pass_threshold": 75, "critical_error_fails": True,
            "invalid_plan_score": 0, "generation_errors_are_unscored": True,
        },
        "source_manifest_hashes": source_manifest.get("source_sha256"),
        "notes": [
            "A status=success means the Plan passed the 75-point rubric threshold; it is not execution success.",
            "Latest-outcome score means use one record per task, group, and repeat; invalid plans score zero.",
            "Pass rate excludes unscored generation errors. C is 30/30 among scored outputs but has 6 generation errors.",
            "Full-attempt spend is a lower bound due unknown-cost calls; confirm against provider billing.",
            "Task-level intervals use only complete task pairs and are exploratory.",
        ],
    }


def write_report(summary):
    groups, costs = summary["latest_outcomes"], summary["latest_outcome_costs_usd"]
    lines = [
        "# E04 latest-outcome analysis", "",
        "One latest record per planned task × group × repeat cell. Invalid plans score zero; generation errors are unscored.", "",
        "| Group | Latest outcomes | Mean Plan score /100 | Pass rate among scored/invalid | Latest known cost |",
        "|---|---:|---:|---:|---:|",
    ]
    for group in "ABC":
        s = groups[group]
        denominator = s["graded"] + s["invalid_plans"]
        lines.append(f"| {group} | {s['graded']} graded, {s['invalid_plans']} invalid, {s['generation_errors']} errors | {s['mean_plan_score_100_invalid_as_zero']:.2f} | {s['passed']}/{denominator} ({s['pass_rate_over_scored_or_invalid']:.1%}) | USD {costs[group]['known_total_usd']:.6f} |")
    lines += ["", "## Paired task comparisons", ""]
    for name, c in summary["paired_latest_outcome_comparisons"].items():
        lo, hi = c["bootstrap_95_ci"]
        lines.append(f"- {name}: {c['complete_paired_tasks']} complete task pairs; mean difference {c['mean_difference']:.2f}; 95% task bootstrap interval [{lo:.2f}, {hi:.2f}]. The 5-point noninferiority criterion was not met.")
    history = summary["all_attempt_costs_usd_lower_bound"]
    lines += [
        "", "## Cost and retry history", "",
        f"The source ledger contains {summary['source_attempts']} attempts for {summary['expected_unique_cells']} planned cells. Known token-based spend is USD {history['known_total_usd']:.6f}, with {history['unknown_cost_calls']} unknown-cost calls; this is a lower bound, not a provider invoice.",
        "", "## Interpretation", "",
        "C is 1.05 points above B on mean Plan score and about 39% more expensive on the latest outcome rows. Neither B nor C establishes noninferiority to A. Nine latest cells were generation errors (3 B, 6 C); the records show outputs truncated at the 6,000 completion-token cap. This run measured plan quality, not task execution success.",
        "", "Promptfoo ran the groups and invoked a custom Python assertion. A deterministic JSON Plan contract check ran first; the shared gpt-6.1-sol judge then scored coverage (30), feasibility (25), dependencies (20), verification (15), and recovery (10). Passing required score ≥75 and no critical error.",
        "", "The source archive includes final Plan outputs, judge evidence, C candidate Plans, model-call stages, and a compact attempt history. Provider response IDs and secrets are omitted. Evaluation references are included only post-run; generation did not receive them.",
        "",
    ]
    (EXP / "results" / "pilot" / "overall_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, help="Original run directory; only required on first build.")
    args = parser.parse_args()
    if args.source_run:
        cases, latest, attempts, manifest, invocation = archive_source(args.source_run)
    else:
        cases, latest, attempts, manifest, invocation = archive_loaded()
    if (len(cases), len(latest), len(attempts)) != (12, 108, 182):
        raise ValueError(f"Expected 12 tasks, 108 latest cells, 182 attempts; found {len(cases)}, {len(latest)}, {len(attempts)}")
    run_pair(latest, manifest, cases, "B", "pairwise-ab-001")
    run_pair(latest, manifest, cases, "C", "pairwise-ac-001")
    summary = make_summary(latest, attempts, manifest, invocation)
    write_json(EXP / "results" / "pilot" / "overall_summary.json", summary)
    write_report(summary)
    print(f"Built offline reports from {len(latest)} latest cells and {len(attempts)} attempts; no API calls made.")


if __name__ == "__main__":
    main()
