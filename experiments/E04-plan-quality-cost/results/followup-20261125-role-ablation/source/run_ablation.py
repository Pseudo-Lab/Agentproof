"""Run the focused C-vs-E ablation without changing the main experiment runner.

C is the remove-role-specialization ablation of E. This script uses the same
cases, generator, judge, validation, API ledger, and pricing config as run.py.
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import random
import shutil
import sys

from benchmark import ROOT, generate, grade, settings, snapshot, write_json
from summarize import summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=3.0,
                        help="Stop starting new samples when known usage reaches this cap")
    parser.add_argument("--seed", type=int, default=20261125,
                        help="Randomizes execution order only; not a model sampling seed")
    args = parser.parse_args()
    if args.repeat < 1 or args.max_cost_usd <= 0:
        parser.error("repeat and max-cost-usd must be positive")

    os.environ["PLAN_MOCK"] = "0"
    cfg = settings()
    missing = {spec["api_key_env"] for spec in cfg["models"].values()
               if not os.environ.get(spec["api_key_env"])}
    if missing:
        parser.error("Set API keys in environment: " + ", ".join(sorted(missing)))

    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8-sig"))
    cases.extend(json.loads((ROOT / "challenge_cases.json").read_text(encoding="utf-8-sig")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    out = ROOT / "runs" / ("real_ablation_C_E_" + stamp)
    os.environ["PLAN_RUN_DIR"] = str(out)
    out.mkdir(parents=True, exist_ok=False)
    (out / "records").mkdir()
    snapshot(cfg, cases)
    shutil.copy2(ROOT / "experiment.toml", out / "experiment.toml")
    write_json(out / "cases.json", cases)
    groups = ["C", "E"]
    write_json(out / "invocation.json", {
        "engine": "python", "experiment": "focused_role_diversity_ablation",
        "repeat": args.repeat, "seed": args.seed,
        "expected_samples": len(cases) * len(groups) * args.repeat,
        "groups": groups, "sample_workers": 1, "challenge_tasks_included": True,
        "max_cost_usd": args.max_cost_usd,
    })
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["groups"] = groups
    manifest["ablation"] = {
        "intervention": "E: three role-diverse low-model candidates plus low-model synthesis",
        "ablation": "C: three homogeneous low-model candidates plus the same synthesis",
        "factor_removed": "planner role diversification",
    }
    write_json(out / "manifest.json", manifest)

    jobs = [(case, repeat, group) for case in cases for repeat in range(args.repeat)
            for group in groups]
    random.Random(args.seed).shuffle(jobs)
    print(f"Run folder: {out}", flush=True)
    print(f"Planned samples: {len(jobs)}; cost cap: ${args.max_cost_usd:.2f}", flush=True)
    completed = 0
    stopped_reason = None
    for case, repeat, group in jobs:
        records = [json.loads(p.read_text(encoding="utf-8"))
                   for p in (out / "records").glob("*.json")]
        known = sum(c.get("cost_usd") or 0 for r in records for c in r.get("calls", []))
        unknown = sum(c.get("cost_usd") is None for r in records for c in r.get("calls", []))
        if unknown:
            stopped_reason = "unknown-cost call recorded; stopped before another sample"
            break
        if known >= args.max_cost_usd:
            stopped_reason = "known usage reached configured cap"
            break
        task_id = case["vars"]["task_id"]
        print(f"{task_id} repeat={repeat + 1}/{args.repeat} condition={group} spent=${known:.4f}", flush=True)
        result = generate(group, case["vars"]["task"], task_id, repeat)
        if "error" in result:
            stopped_reason = "generation error; inspect recorded attempt before resuming"
            break
        try:
            grade(result["output"], case["vars"], result["metadata"])
        except Exception:
            stopped_reason = "judge error; inspect recorded attempt before resuming"
            break
        completed += 1

    summary = summarize(out)
    if stopped_reason:
        summary["stopped_reason"] = stopped_reason
        write_json(out / "summary.json", summary)
    print(f"Completed samples: {completed}/{len(jobs)}", flush=True)
    print(f"Known estimated spend: ${summary['experiment_cost_usd']:.6f}; "
          f"unknown-cost calls: {summary['unknown_cost_calls']}", flush=True)
    print(f"Summary: {out / 'summary.md'}", flush=True)
    return 0 if completed == len(jobs) else 2


if __name__ == "__main__":
    sys.exit(main())
