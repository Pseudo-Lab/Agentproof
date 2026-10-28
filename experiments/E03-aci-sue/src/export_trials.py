"""Convert published mini trajectories and official SWE-bench reports offline.

No model, Docker, network, or new grader. Agentproof's unchanged summarizer
validates the grid. --write creates the two derived files; default checks them.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]
spec = importlib.util.spec_from_file_location("agentproof_summary", REPO / "harness/summarize.py")
summary_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary_module)


def classify(task, official, exit_status):
    if task in official["error_ids"]:
        return "error", 0
    if exit_status == "TimeExceeded":
        return "timeout", int(task in official["resolved_ids"])
    if task in official["resolved_ids"]:
        return "success", 1
    if task in official["unresolved_ids"] or task in official["empty_patch_ids"]:
        return "failure", 0
    raise ValueError(f"Official outcome is missing: {task}")


def convert(run):
    manifest = json.loads((run / "manifest.json").read_text())
    for name, metadata in manifest["artifacts"].items():
        data = (run / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == metadata["public_sha256"], name
    rows = []
    for condition in ("baseline", "intervention"):
        report_path = f"{condition}/official-report.json"
        official = json.loads((run / report_path).read_text())
        predictions = json.loads((run / condition / "preds.json").read_text())
        assert official["total_instances"] == len(manifest["task_ids"])
        assert set(predictions) == set(manifest["task_ids"])
        for task in manifest["task_ids"]:
            trajectory_path = f"{condition}/{task}.traj.json"
            trajectory = json.loads((run / trajectory_path).read_text())
            assert trajectory["instance_id"] == task
            messages = trajectory["messages"]
            exits = [m for m in messages if m["role"] == "exit"]
            assert len(exits) == 1
            elapsed = exits[0]["extra"]["elapsed_seconds"]
            info = trajectory["info"]
            assert info["submission"] == predictions[task]["model_patch"]
            responses = [m["extra"]["response"] for m in messages if "response" in m.get("extra", {})]
            assert len(responses) == info["model_stats"]["api_calls"]
            assert all(isinstance(r.get("usage", {}).get(k), int) for r in responses
                       for k in ("prompt_tokens", "completion_tokens"))
            status, score = classify(task, official, info["exit_status"])
            grading = run / condition / "grading" / f"{task}.json"
            evidence = {"trajectory": trajectory_path, "official_report": report_path,
                        "predictions": f"{condition}/preds.json"}
            if grading.exists():
                detail = json.loads(grading.read_text())[task]
                assert detail["resolved"] == bool(score)
                evidence["official_task_report"] = str(grading.relative_to(run))
            else:
                assert task in official["empty_patch_ids"] and not info["submission"].strip()
            rows.append({
                "run_id": manifest["run_id"], "task_id": task, "condition": condition, "repeat_id": 1,
                "status": status, "score": score, "latency_ms": elapsed * 1000,
                "input_tokens": sum(r["usage"]["prompt_tokens"] for r in responses),
                "output_tokens": sum(r["usage"]["completion_tokens"] for r in responses),
                "cost_usd": None,
                "missing_reasons": {"cost_usd": "Local GPU electricity/amortization not measured; native zero is a placeholder."},
                "evidence": evidence, "api_calls": info["model_stats"]["api_calls"],
                "native_exit_status": info["exit_status"],
            })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    provenance = json.loads((PACKAGE / "results/provenance/source-code.json").read_text())
    for name, digest in provenance["files"].items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == digest, name
    for run in sorted((PACKAGE / "results/pilot").iterdir()):
        rows = convert(run)
        trials = run / "trials.jsonl"
        if args.write:
            trials.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        else:
            assert rows == [json.loads(line) for line in trials.read_text().splitlines()]
        result = summary_module.summarize(run)
        summary = run / "summary.json"
        if args.write:
            summary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        else:
            assert result == json.loads(summary.read_text())
        print(f"OK {run.name}: {len(rows)} real historical trials; hashes, patches, grades, metrics and summary agree")


if __name__ == "__main__":
    main()
