"""Run the exact same pipeline with Promptfoo or a dependency-free smoke runner."""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from benchmark import GROUPS, ROOT, generate, grade, run_dir, settings, snapshot, write_json
from summarize import summarize


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="No API calls, synthetic scores, zero actual spend")
    parser.add_argument("--engine", choices=["promptfoo", "python"], default="promptfoo")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--sample-workers", type=int, default=1,
                        help="Run independent task × condition samples concurrently (Python engine only)")
    parser.add_argument("--limit", type=int, help="Use only the first N tasks")
    parser.add_argument("--config", type=Path, default=ROOT / "experiment.toml")
    parser.add_argument("--cases", type=Path, default=ROOT / "cases.json")
    parser.add_argument("--include-challenge", action="store_true",
                        help="Append the frozen challenge scenarios; smoke/mock cases remain separate")
    parser.add_argument("--layer", action="append", help="Select a task_layer; repeat to include multiple layers")
    parser.add_argument("--seed", type=int, default=42, help="Order randomization only; not a model sampling seed")
    parser.add_argument("--promptfoo-cli", type=Path, help="Optional installed Promptfoo entrypoint.js; run with node")
    parser.add_argument("--bridge", action="store_true", help="Use localhost Python bridge instead of Node spawning Python")
    args = parser.parse_args()
    if args.repeat < 1 or args.limit is not None and args.limit < 1 or args.sample_workers < 1:
        parser.error("repeat, limit, and sample-workers must be positive")
    os.environ["PLAN_CONFIG"] = str(args.config.resolve())
    os.environ["PLAN_MOCK"] = "1" if args.mock else "0"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    os.environ["PLAN_RUN_DIR"] = str(ROOT / "runs" / (("mock_" if args.mock else "real_") + stamp))
    directory = run_dir()
    cfg = settings()
    cases = json.loads(args.cases.read_text(encoding="utf-8-sig"))
    if args.include_challenge:
        challenges = json.loads((ROOT / "challenge_cases.json").read_text(encoding="utf-8-sig"))
        cases.extend(challenges)
    ids = [c["vars"]["task_id"] for c in cases]
    if len(set(ids)) != len(ids):
        parser.error("task_id must be unique")
    for c in cases:
        for key in ("task_id", "task", "eval_reference"):
            if not isinstance(c["vars"].get(key), str) or not c["vars"][key].strip():
                parser.error(f"Invalid case variable: {key}")
        layer = c["vars"].get("task_layer", "unclassified")
        if not isinstance(layer, str) or not layer.strip():
            parser.error("Invalid case variable: task_layer")
    if args.layer:
        available = {c["vars"].get("task_layer", "unclassified") for c in cases}
        unknown = set(args.layer) - available
        if unknown:
            parser.error("Unknown task layers: " + ", ".join(sorted(unknown))
                         + ". Available: " + ", ".join(sorted(available)))
        cases = [c for c in cases if c["vars"].get("task_layer", "unclassified") in args.layer]
    cases = cases[:args.limit] if args.limit else cases
    if not args.mock:
        missing = {s["api_key_env"] for s in cfg["models"].values() if not os.environ.get(s["api_key_env"])}
        if missing:
            parser.error("Set API keys in environment: " + ", ".join(sorted(missing)))
    snapshot(cfg, cases)
    shutil.copy2(args.config, directory / "experiment.toml")
    write_json(directory / "cases.json", cases)
    write_json(directory / "invocation.json", {"engine": args.engine, "repeat": args.repeat, "seed": args.seed,
                                               "expected_samples": len(cases) * len(GROUPS) * args.repeat,
                                               "groups": list(GROUPS),
                                               "sample_workers": args.sample_workers,
                                               "challenge_tasks_included": args.include_challenge})
    print(f"{'MOCK: SYNTHETIC RESULTS' if args.mock else 'REAL API EXPERIMENT'}\nOutput: {directory}", flush=True)
    rng = random.Random(args.seed)
    exit_code = 0
    if args.engine == "python":
        jobs = [(case, repeat, group) for case in cases for repeat in range(args.repeat) for group in GROUPS]
        rng.shuffle(jobs)
        def process_job(job):
            case, repeat, group = job
            print(f"{case['vars']['task_id']} repeat={repeat} group={group}", flush=True)
            response = generate(group, case["vars"]["task"], case["vars"]["task_id"], repeat)
            if "error" in response:
                return 1
            try:
                grade(response["output"], case["vars"], response["metadata"])
            except Exception as exc:
                print(str(exc), file=sys.stderr)
                return 1
            return 0
        with ThreadPoolExecutor(max_workers=args.sample_workers) as pool:
            futures = [pool.submit(process_job, job) for job in jobs]
            for future in as_completed(futures):
                exit_code = max(exit_code, future.result())
    else:
        # JSON is valid YAML; no PyYAML dependency required. Paths are absolute.
        provider_file = "bridge_provider.cjs" if args.bridge else "provider.py"
        assertion_file = "bridge_assert.js" if args.bridge else "judge.py"
        labels = {"A": "high_single", "B": "low_single", "C": "low_ensemble_n3",
                  "D": "low_ensemble_n5", "E": "low_role_diverse_n3"}
        providers = [{"id": "file://" + (ROOT / provider_file).as_posix(),
                      "label": f"{g}_{labels[g]}", "config": {"group": g}} for g in GROUPS]
        rng.shuffle(providers)
        rng.shuffle(cases)
        config = {"description": "MOCK synthetic" if args.mock else "A/B/C/D/E plan-only benchmark",
                  "prompts": ["{{task}}"], "providers": providers, "tests": cases,
                  "defaultTest": {"assert": [{"type": "javascript" if args.bridge else "python", "metric": "plan_quality",
                                               "value": "file://" + Path(os.path.relpath(ROOT / assertion_file, directory)).as_posix()}]},
                  "evaluateOptions": {"maxConcurrency": 1}}
        config_path = directory / "promptfooconfig.yaml"
        write_json(config_path, config)
        os.environ.setdefault("PROMPTFOO_PYTHON", sys.executable)
        os.environ["PYTHONPATH"] = str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
        os.environ.setdefault("PROMPTFOO_DISABLE_TELEMETRY", "1")
        os.environ.setdefault("PROMPTFOO_CONFIG_DIR", str(directory / "promptfoo-home"))
        if args.promptfoo_cli:
            prefix = [shutil.which("node") or "node", str(args.promptfoo_cli.resolve())]
        elif (ROOT / "node_modules" / "promptfoo" / "dist" / "src" / "entrypoint.js").exists():
            prefix = [shutil.which("node") or "node",
                      str(ROOT / "node_modules" / "promptfoo" / "dist" / "src" / "entrypoint.js")]
        elif shutil.which("promptfoo"):
            prefix = [shutil.which("promptfoo")]
        elif shutil.which("npx"):
            prefix = [shutil.which("npx"), "--yes", "promptfoo@0.124.1"]
        elif shutil.which("pnpm"):
            prefix = [shutil.which("pnpm"), "dlx", "promptfoo@0.124.1"]
        else:
            parser.error("Install Node.js + npx, or use --engine python (same pipeline, no Promptfoo UI).")
        version = subprocess.run(prefix + ["--version"], cwd=ROOT, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace")
        (directory / "promptfoo-version.txt").write_text(version.stdout + version.stderr, encoding="utf-8")
        command = prefix + ["eval", "-c", str(config_path), "--no-cache", "--repeat", str(args.repeat),
                            "--max-concurrency", "1", "-o", str(directory / "promptfoo-results.json")]
        server = None
        if args.bridge:
            from bridge import start_bridge
            server = start_bridge()
        try:
            exit_code = subprocess.run(command, cwd=ROOT).returncode
        finally:
            if server:
                server.shutdown()
                server.server_close()
    summarize(directory)
    print(f"Report: {directory / 'summary.md'}", flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
