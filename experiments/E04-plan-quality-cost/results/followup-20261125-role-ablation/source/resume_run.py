"""Resume missing or interrupted samples in an existing benchmark run directory."""
import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from benchmark import GROUPS, generate, grade
from summarize import summarize


TERMINAL = {"graded", "invalid_plan"}


def record_key(record):
    return record["task_id"], record["group"], record["repeat"]


def resume(directory, sample_workers=3):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    cases = json.loads((directory / "cases.json").read_text(encoding="utf-8-sig"))
    invocation_path = directory / "invocation.json"
    invocation = json.loads(invocation_path.read_text(encoding="utf-8"))
    config_path = directory / "experiment.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing saved config: {config_path}")

    os.environ["PLAN_CONFIG"] = str(config_path)
    os.environ["PLAN_RUN_DIR"] = str(directory)
    os.environ["PLAN_MOCK"] = "1" if manifest.get("mock") else "0"

    records_dir = directory / "records"
    latest = {}
    for path in records_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = record_key(record)
        if key not in latest or path.stat().st_mtime > latest[key][0].stat().st_mtime:
            latest[key] = (path, record)

    retries = []
    for case in cases:
        variables = case["vars"]
        for repeat in range(invocation["repeat"]):
            for group in invocation.get("groups", GROUPS):
                key = (variables["task_id"], group, repeat)
                previous = latest.get(key)
                if previous and previous[1].get("status") in TERMINAL:
                    continue
                retries.append((case, repeat, group, previous))

    print(f"Resuming {directory}: {len(retries)} sample keys need completion.", flush=True)
    invocation.setdefault("resumptions", []).append({
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_workers": sample_workers,
        "pending_sample_keys": len(retries),
        "previous_record_keys": len(latest),
    })
    invocation_path.write_text(json.dumps(invocation, ensure_ascii=False, indent=2), encoding="utf-8")
    def process_retry(job):
        case, repeat, group, previous = job
        variables = case["vars"]
        if previous:
            path, record = previous
            output = record.get("output")
            if output and record.get("status") in {"generated", "judge_error"}:
                metadata = {"group": group, "sample_id": record["sample_id"],
                            "record_path": str(path), "mock": manifest.get("mock", False)}
                try:
                    grade(output, variables, metadata)
                except RuntimeError:
                    pass  # The judge failure is persisted and can be retried later.
                return
            if record.get("status") in {"running", "generated"}:
                record["status"] = "interrupted"
                record["error"] = "Run was interrupted before grading; retained for cost accounting."
                path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        response = generate(group, variables["task"], variables["task_id"], repeat)
        if "error" in response:
            return
        try:
            grade(response["output"], variables, response["metadata"])
        except RuntimeError:
            pass  # The judge failure is persisted and can be retried later.

    with ThreadPoolExecutor(max_workers=sample_workers) as pool:
        futures = [pool.submit(process_retry, job) for job in retries]
        for future in as_completed(futures):
            future.result()

    summarize(directory)
    print(f"Saved updated summary: {directory / 'summary.md'}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--sample-workers", type=int, default=3,
                        help="Run independent missing task × condition samples concurrently")
    args = parser.parse_args()
    if args.sample_workers < 1:
        parser.error("sample-workers must be positive")
    resume(args.run_directory, args.sample_workers)
