"""3순위 과제 묶음: SWE-bench Lite 에서 정답 패치가 작은 과제를 뽑아 data/ 에 쓴다.

사용법 (실험 폴더 기준):
  python3 src/prepare_swebench.py --source <SWE-bench_Lite test split jsonl> --n 10 --seed 20261029 \
      --out data/tasks_swebench_pilot.json

원본: https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite (test split, 300개)
선정 규칙: 정답 패치(`patch`)의 변경 줄(+/-, 헤더 제외)이 10 이하이고 바꾸는 파일이 1개이며,
`--verified-ids` 를 주면 SWE-bench Verified(사람이 테스트를 검수한 500개)에도 들어 있는 과제 중
seed 로 무작위 n개. 저장소별 비율을 맞추지 않는다(원 분포를 따름).
Verified 교집합으로 좁히는 이유: Lite 의 psf__requests-863 처럼 숨겨진 테스트가 외부 네트워크에 의존해
틀린 패치도 통과시키는 과제가 있다(채점기 검증에서 발견).

에이전트에게 보여 주는 것: problem_statement 와 저장소(/testbed, 이미지에 들어 있음).
보여 주지 않는 것: patch(정답), test_patch, FAIL_TO_PASS / PASS_TO_PASS, eval_script.
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]
HIDDEN_KEYS = ("patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS", "eval_script", "log_parser",
               "eval_type", "environment_setup_commit")


def changed_lines(patch: str) -> int:
    return sum(1 for l in patch.splitlines()
               if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--source-commit", default=None, help="HF 데이터셋 commit (기록용)")
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--max-changed-lines", type=int, default=10)
    ap.add_argument("--exclude", help="제외할 instance_id 가 든 tasks json")
    ap.add_argument("--verified-ids", help="SWE-bench Verified instance_id 목록(json 배열). 주면 교집합만 쓴다")
    ap.add_argument("--verified-commit", default=None, help="Verified 데이터셋 commit (기록용)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    src = Path(args.source)
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: r["instance_id"])
    excluded = set()
    if args.exclude:
        excluded = {t["source_id"] for t in json.loads(Path(args.exclude).read_text())["tasks"]}
    verified = set(json.loads(Path(args.verified_ids).read_text())) if args.verified_ids else None
    pool = [r for r in rows if changed_lines(r["patch"]) <= args.max_changed_lines
            and r["patch"].count("diff --git") == 1 and r["instance_id"] not in excluded
            and (verified is None or r["instance_id"] in verified)]
    chosen = sorted(random.Random(args.seed).sample(pool, args.n), key=lambda r: r["instance_id"])
    tasks = [{
        "task_id": r["instance_id"],
        "source_id": r["instance_id"],
        "kind": "swebench",
        "issue": r["problem_statement"],
        "repo": {"image": r["image"], "cwd": "/testbed", "repo": r["repo"], "version": r["version"],
                 "base_commit": r["base_commit"]},
        "hidden_test": {k: r[k] for k in HIDDEN_KEYS},
        "reference": {"changed_lines": changed_lines(r["patch"]), "difficulty": r.get("difficulty"),
                      "note": "채점 전용. 에이전트에게 보여 주지 않는다."},
    } for r in chosen]
    out = {
        "source": {"dataset": "SWE-bench/SWE-bench_Lite", "split": "test", "commit": args.source_commit,
                   "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "license": "MIT", "total_rows": len(rows)},
        "selection": {"n": args.n, "seed": args.seed, "pool_size": len(pool),
                      "rule": f"changed lines <= {args.max_changed_lines} and exactly 1 file in gold patch"
                              + (" and also in SWE-bench Verified" if verified is not None else ""),
                      "verified_filter": None if verified is None else {
                          "dataset": "SWE-bench/SWE-bench_Verified", "commit": args.verified_commit,
                          "n_ids": len(verified)},
                      "excluded_source_ids": sorted(excluded)},
        "tasks": tasks,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"pool {len(pool)} -> {len(tasks)} tasks -> {args.out}")
    for t in tasks:
        print(f"  {t['task_id']:<40} {t['reference']['changed_lines']:>2} lines  {t['reference']['difficulty']}")


if __name__ == "__main__":
    main()
