"""SWE-bench 과제 묶음의 채점 가능성 검증 (에이전트 실행 전에 한 번).

과제마다 (1) 정답 패치 → resolved, (2) 정답 패치가 바꾸는 파일 끝에 주석 한 줄만 붙인 무의미 패치
→ unresolved 인지 공식 하네스로 확인한다. 둘 다 만족하지 않는 과제는 숨겨진 테스트가 수정 여부를
가려내지 못하므로 쓰지 않는다. 이미지는 Apple Silicon 에서 `--platform linux/amd64` 로 미리 받는다
(하네스는 플랫폼을 지정하지 않고 받으려다 실패한다).

사용법 (레포 루트, .venv):
  .venv/bin/python experiments/E01-tool-output-compression/src/validate_swebench.py \
      --tasks experiments/E01-tool-output-compression/data/tasks_swebench_pilot.json \
      --out experiments/E01-tool-output-compression/results/pilot/swebench-validation.json
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def noop_patch(image: str, path: str) -> str:
    script = f"cd /testbed && printf '\\n# e01 noop\\n' >> {path} && git -c core.fileMode=false diff"
    p = sh(["docker", "run", "--rm", "--platform", "linux/amd64", image, "bash", "-c", script], timeout=600)
    if p.returncode != 0 or "e01 noop" not in p.stdout:
        raise RuntimeError(f"noop patch failed for {image}: {p.stdout[-500:]} {p.stderr[-500:]}")
    return p.stdout


def evaluate(preds: list, dataset: str, run_id: str, workdir: Path) -> dict:
    f = workdir / f"{run_id}.json"
    f.write_text(json.dumps(preds))
    ids = [x["instance_id"] for x in preds]
    p = sh([sys.executable, "-m", "swebench.harness.run_evaluation", "--dataset_name", dataset, "--split", "test",
            "--instance_ids", *ids, "--predictions_path", str(f), "--max_workers", "2", "--run_id", run_id,
            "--timeout", "1800", "--report_dir", str(workdir)], cwd=workdir, timeout=7200)
    rep = workdir / f"{preds[0]['model_name_or_path']}.{run_id}.json"
    if not rep.exists():
        raise RuntimeError(f"no report: {p.stdout[-1500:]} {p.stderr[-1500:]}")
    return json.loads(rep.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    doc = json.loads(Path(args.tasks).read_text())
    dataset = doc["source"]["dataset"]
    tasks = doc["tasks"]
    for t in tasks:
        img = t["repo"]["image"]
        p = sh(["docker", "pull", "-q", "--platform", "linux/amd64", img], timeout=1800)
        print(f"pull {t['task_id']}: {'ok' if p.returncode == 0 else p.stderr.strip()[-200:]}", flush=True)
    gold, noop = [], []
    for t in tasks:
        path = re.search(r"^diff --git a/(\S+)", t["hidden_test"]["patch"], re.M).group(1)
        gold.append({"instance_id": t["task_id"], "model_name_or_path": "gold", "model_patch": t["hidden_test"]["patch"]})
        noop.append({"instance_id": t["task_id"], "model_name_or_path": "noop", "model_patch": noop_patch(t["repo"]["image"], path)})
    with tempfile.TemporaryDirectory() as tmp:
        g = evaluate(gold, dataset, "validate-gold", Path(tmp))
        n = evaluate(noop, dataset, "validate-noop", Path(tmp))
    rows = []
    for t in tasks:
        iid = t["task_id"]
        gs = "resolved" if iid in g["resolved_ids"] else ("error" if iid in g["error_ids"] else "unresolved")
        ns = "resolved" if iid in n["resolved_ids"] else ("error" if iid in n["error_ids"] else "unresolved")
        rows.append({"task_id": iid, "gold": gs, "noop": ns, "usable": gs == "resolved" and ns == "unresolved"})
        print(f"{iid:<40} gold={gs:<10} noop={ns:<10} {'OK' if rows[-1]['usable'] else 'EXCLUDE'}", flush=True)
    out = {"tasks_file": Path(args.tasks).name, "dataset": dataset, "harness": "swebench.harness.run_evaluation",
           "rule": "usable iff gold patch resolved and comment-only patch unresolved", "results": rows}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"usable {sum(r['usable'] for r in rows)}/{len(rows)} -> {args.out}")


if __name__ == "__main__":
    main()
