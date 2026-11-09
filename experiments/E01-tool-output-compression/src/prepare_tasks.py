"""HumanEvalPack(파이썬) 에서 과제를 뽑아 data/tasks.json 을 만든다.

사용법 (실험 폴더에서):
  python3 src/prepare_tasks.py --source <humanevalpack python parquet> --split pilot --n 10 --seed 20261026

원본: https://huggingface.co/datasets/bigcode/humanevalpack  (python/test-00000-of-00001.parquet, MIT)
pyarrow 가 필요하다. 네트워크 호출은 하지 않는다. 파일은 미리 내려받아 경로로 넘긴다.

에이전트에게 보여 주는 것: repo.content (버그가 있는 함수 파일), issue.
에이전트에게 보여 주지 않는 것: hidden_test, reference (채점과 mock 전용).
"""
import argparse
import hashlib
import json
import random
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]
SOURCE_REPO = "bigcode/humanevalpack"
SOURCE_FILE = "python/test-00000-of-00001.parquet"


def to_task(r: dict) -> dict:
    content = r["prompt"] + r["buggy_solution"]
    issue = (f"`{r['entry_point']}` in `solution.py` does not behave as described in its docstring.\n"
             f"Fix the bug. Keep the function name and signature unchanged.")
    return {
        "task_id": r["task_id"].replace("/", "-"),
        "source_id": r["task_id"],
        "issue": issue,
        "repo": {"file": "solution.py", "content": content},
        "hidden_test": {"imports": r["import"], "setup": r["test_setup"],
                        "entry_point": r["entry_point"], "test": r["test"]},
        "reference": {"canonical_solution": r["canonical_solution"], "bug_type": r["bug_type"],
                      "note": "채점과 mock 전용. 에이전트에게 보여 주지 않는다."},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="내려받은 parquet 경로")
    ap.add_argument("--source-commit", default="9a41762f73a8cb23bb5811b73d5aab164efcf378",
                    help="데이터셋 저장소 commit (HF API 로 확인한 값)")
    ap.add_argument("--split", choices=("pilot", "main"), required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--exclude", help="제외할 task_id 목록이 든 tasks.json (본 실험에서 예비 과제 제외용)")
    ap.add_argument("--out", default=str(EXPERIMENT / "data/tasks.json"))
    args = ap.parse_args()

    import pyarrow.parquet as pq  # 선택 의존성. 이 스크립트에서만 쓴다.
    src = Path(args.source)
    rows = pq.read_table(src).to_pylist()
    rows.sort(key=lambda r: int(r["task_id"].split("/")[1]))
    excluded = set()
    if args.exclude:
        excluded = {t["source_id"] for t in json.loads(Path(args.exclude).read_text())["tasks"]}
    pool = [r for r in rows if r["task_id"] not in excluded]
    rng = random.Random(args.seed)
    chosen = sorted(rng.sample(pool, args.n), key=lambda r: int(r["task_id"].split("/")[1]))

    out = {
        "source": {"dataset": SOURCE_REPO, "file": SOURCE_FILE, "commit": args.source_commit,
                   "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "license": "MIT",
                   "total_rows": len(rows)},
        "selection": {"split": args.split, "n": args.n, "seed": args.seed,
                      "excluded_source_ids": sorted(excluded),
                      "method": "random.Random(seed).sample over rows sorted by task number, after exclusion"},
        "tasks": [to_task(r) for r in chosen],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(chosen)} tasks -> {args.out}")
    print(" ".join(t["task_id"] for t in out["tasks"]))


if __name__ == "__main__":
    main()
