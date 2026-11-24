"""Summarize ledgers, including failed generations and their known costs."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import random
import statistics


def mean(items):
    return statistics.mean(items) if items else None


def bootstrap(diffs, seed=42):
    if len(diffs) < 2:
        return None
    rng = random.Random(seed)
    samples = sorted(statistics.mean(rng.choices(diffs, k=len(diffs))) for _ in range(4000))
    return [samples[99], samples[3899]]


def aggregate(attempt_rows, latest_rows, manifest, repeat):
    groups_order = manifest.get("groups", ["A", "B", "C"])
    groups = {}
    for g in groups_order:
        attempts = [r for r in attempt_rows if r["group"] == g]
        outcomes = [r for r in latest_rows if r["group"] == g]
        valid = [r for r in outcomes if r["status"] in ("graded", "invalid_plan")]
        semantically_graded = [r for r in outcomes if r["status"] == "graded"]
        groups[g] = {"attempts": len(attempts), "latest_outcomes": len(outcomes), "scored": len(valid),
                     "generation_errors": sum(r["status"] == "generation_error" for r in outcomes),
                     "generation_errors_all_attempts": sum(r["status"] == "generation_error" for r in attempts),
                     "judge_errors": sum(r["status"] == "judge_error" for r in outcomes),
                     "judge_errors_all_attempts": sum(r["status"] == "judge_error" for r in attempts),
                     "invalid_plans": sum(r["status"] == "invalid_plan" for r in outcomes),
                     "mean_score_100": mean([r["score_100"] for r in valid]),
                     "pass_rate_scored": mean([int(r["pass"]) for r in valid]),
                     "judge_critical_rate": mean([int(r["critical"]) for r in semantically_graded]),
                     # Spend includes every recorded attempt, including retries; quality uses only the latest outcome per planned cell.
                     "generation_cost_usd": sum(r["generation_cost_usd"] for r in attempts),
                     "judge_cost_usd": sum(r["judge_cost_usd"] for r in attempts),
                     "total_cost_usd": sum(r["total_cost_usd"] for r in attempts),
                     "mean_generation_latency_ms": mean([r["generation_latency_ms"] for r in outcomes]),
                     "mean_generation_cost_usd": mean([r["generation_cost_usd"] for r in outcomes]),
                     "mean_total_cost_usd": mean([r["total_cost_usd"] for r in outcomes]),
                     "unknown_cost_calls": sum(r["unknown_cost_calls"] for r in attempts)}
    # Paired task means: repeats stay clustered by task, not treated as independent tasks.
    task_scores = defaultdict(lambda: defaultdict(list))
    for r in latest_rows:
        if r["score_100"] is not None:
            task_scores[r["task_id"]][r["group"]].append(r["score_100"])
    margin = manifest["settings"]["experiment"]["noninferiority_margin"]
    comparisons = {}
    for g in groups_order:
        if g == "A":
            continue
        complete = [v for v in task_scores.values() if v["A"] and v[g]
                    and (repeat is None or len(v["A"]) == repeat and len(v[g]) == repeat)]
        diffs = [mean(v[g]) - mean(v["A"]) for v in complete]
        ci = bootstrap(diffs)
        comparisons[g + "-A"] = {"complete_paired_tasks": len(diffs), "mean_difference": mean(diffs),
                                   "bootstrap_95_ci": ci, "margin": margin,
                                   "quality_noninferiority_signal": None if manifest["mock"] else bool(ci and ci[0] > -margin)}
    return {"groups": groups, "comparisons": comparisons}


def summarize(directory):
    directory = Path(directory)
    record_paths = sorted((directory / "records").glob("*.json"), key=lambda p: (p.stat().st_mtime_ns, p.name))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in record_paths]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    invocation_path = directory / "invocation.json"
    invocation = json.loads(invocation_path.read_text()) if invocation_path.exists() else {}
    expected = invocation.get("expected_samples")
    cases_path = directory / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8-sig")) if cases_path.exists() else []
    task_layers = {c["vars"]["task_id"]: c["vars"].get("task_layer", "unclassified") for c in cases}
    rows = []
    latest_paths = {}
    for path, rec in zip(record_paths, records):
        key = (rec["task_id"], rec["group"], rec["repeat"])
        latest_paths[key] = path
    for path, rec in zip(record_paths, records):
        gen = [c for c in rec["calls"] if c["stage"] != "judge"]
        judge = [c for c in rec["calls"] if c["stage"] == "judge"]
        rows.append({"sample_id": rec["sample_id"], "task_id": rec["task_id"], "repeat": rec["repeat"],
                     "task_layer": task_layers.get(rec["task_id"], "unclassified"),
                     "group": rec["group"], "status": rec["status"],
                     "is_latest_outcome": path == latest_paths[(rec["task_id"], rec["group"], rec["repeat"])],
                     "score_100": rec.get("score_100"),
                     "pass": (rec.get("grade") or {}).get("pass"), "critical": rec.get("critical"),
                     "generation_cost_usd": sum(c["cost_usd"] or 0 for c in gen),
                     "judge_cost_usd": sum(c["cost_usd"] or 0 for c in judge),
                     "total_cost_usd": sum(c["cost_usd"] or 0 for c in rec["calls"]),
                     "unknown_cost_calls": sum(c["cost_usd"] is None for c in rec["calls"]),
                     "generation_calls": len(gen), "judge_calls": len(judge),
                     "generation_latency_ms": rec.get("generation_latency_ms", 0)})
    columns = list(rows[0]) if rows else ["sample_id", "task_layer", "status"]
    with (directory / "samples.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    repeat = invocation.get("repeat")
    groups_order = invocation.get("groups", manifest.get("groups", ["A", "B", "C"]))
    manifest["groups"] = groups_order
    latest_rows = [r for r in rows if r["is_latest_outcome"]]
    overall = aggregate(rows, latest_rows, manifest, repeat)
    groups, comparisons = overall["groups"], overall["comparisons"]
    layers = {}
    for layer in sorted(set(task_layers.values()) | {r["task_layer"] for r in rows}):
        attempt_subset = [r for r in rows if r["task_layer"] == layer]
        latest_subset = [r for r in latest_rows if r["task_layer"] == layer]
        task_count = sum(value == layer for value in task_layers.values())
        layer_expected = task_count * len(groups_order) * repeat if cases and repeat is not None else None
        layers[layer] = {**aggregate(attempt_subset, latest_subset, manifest, repeat), "task_count": task_count if cases else None,
                         "expected_samples": layer_expected, "recorded_samples": len(latest_subset),
                         "missing_samples": max(0, layer_expected - len(latest_subset)) if layer_expected is not None else None}
    summary = {"mock": manifest["mock"], "expected_samples": expected, "recorded_samples": len(latest_rows),
               "attempt_records": len(rows),
               "missing_samples": max(0, expected - len(latest_rows)) if expected is not None else None,
               "groups": groups, "comparisons": comparisons, "layers": layers,
               "experiment_cost_usd": sum(r["total_cost_usd"] for r in rows),
               "unknown_cost_calls": sum(r["unknown_cost_calls"] for r in rows)}
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    def fmt(value, digits=2):
        return "N/A" if value is None else f"{value:.{digits}f}"
    lines = ["# " + ("MOCK ONLY — synthetic scores, not model performance" if manifest["mock"] else "Plan benchmark"),
             "", f"Latest planned cells: {len(latest_rows)} / {expected if expected is not None else 'unknown'}; recorded attempt records: {len(rows)}. All costs are USD estimates.", "",
             "| Group | Latest outcomes | Scored | Plan /100 | Pass rate | All attempt records | Generation $ | Judge $ | Total known $ | Unknown-cost calls |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for g, v in groups.items():
        lines.append(f"| {g} | {v['latest_outcomes']} | {v['scored']} | {fmt(v['mean_score_100'])} | "
                     f"{fmt(v['pass_rate_scored'])} | {v['attempts']} | {v['generation_cost_usd']:.6f} | "
                     f"{v['judge_cost_usd']:.6f} | {v['total_cost_usd']:.6f} | {v['unknown_cost_calls']} |")
    lines += ["", f"All groups combined known spend across {len(rows)} recorded sample attempts: ${summary['experiment_cost_usd']:.6f}; "
              f"unknown-cost calls: {summary['unknown_cost_calls']}.", ""]
    for g, v in groups.items():
        lines.append(f"- {g}: latest generation errors={v['generation_errors']} (all attempts={v['generation_errors_all_attempts']}); "
                     f"latest judge errors={v['judge_errors']} (all attempts={v['judge_errors_all_attempts']}); "
                     f"invalid plans={v['invalid_plans']}; judge critical-error rate={fmt(v['judge_critical_rate'])}; "
                     f"mean generation cost=${fmt(v['mean_generation_cost_usd'], 6)}.")
    lines += ["", "Cost per sample, individual plans, grader evidence, errors and call details are in samples.csv and records/.",
              "Unknown-cost calls make displayed spend a lower bound; a timeout may still have been billed.",
              "Generation errors and judge failures are counted separately and excluded from mean quality.",
              "Invalid plan contracts score zero; critical semantic errors also fail even if the score is high.", "",
              "## Paired comparisons", ""]
    for name, value in comparisons.items():
        lines.append(f"- {name}: task pairs={value['complete_paired_tasks']}; delta={fmt(value['mean_difference'])}; "
                     f"95% task-cluster bootstrap CI={value['bootstrap_95_ci']}; margin={value['margin']} points.")
    lines += ["", "## Task layers", "",
              "| Layer | Group | Latest outcomes / expected | All attempt records | Scored | Plan /100 | Pass rate | Generation $ | Judge $ | Unknown-cost calls |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for layer, data in layers.items():
        per_group = data["task_count"] * repeat if repeat is not None else "?"
        for g, v in data["groups"].items():
            lines.append(f"| {layer} | {g} | {v['latest_outcomes']} / {per_group} | {v['attempts']} | {v['scored']} | "
                         f"{fmt(v['mean_score_100'])} | {fmt(v['pass_rate_scored'])} | "
                         f"{v['generation_cost_usd']:.6f} | {v['judge_cost_usd']:.6f} | {v['unknown_cost_calls']} |")
    for layer, data in layers.items():
        for name, value in data["comparisons"].items():
            lines.append(f"- {layer}, {name}: task pairs={value['complete_paired_tasks']}; "
                         f"delta={fmt(value['mean_difference'])}; 95% CI={value['bootstrap_95_ci']}.")
    lines += ["", "These intervals are exploratory. Example tasks and small layer subsets are pilot data, not evidence of equivalence.",
              "A quality noninferiority signal alone does not establish cheaper or equally reliable performance.",
              "Review missing/error rates, critical errors, and generation cost before concluding. Human evaluation is not part of this run.",
              "This run measures achieved quality and cost, not equal-dollar-budget performance."]
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    print(json.dumps(summarize(parser.parse_args().run_directory), ensure_ascii=False, indent=2))
