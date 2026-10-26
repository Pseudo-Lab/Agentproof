"""2순위 과제 묶음: HumanEvalFix 버그 함수를 여러 파일짜리 패키지 안에 숨긴다.

사용법 (실험 폴더 기준, pyarrow 필요):
  python3 src/wrap_tasks.py --source <humanevalpack python parquet> --targets data/tasks.json \
      --out data/tasks_wrapped_pilot.json --seed 20261028

포장 규칙 (모든 과제에 똑같이, 사람 손 없이 seed 로 결정):
- 패키지 이름은 `toolkit`, 모듈 8개(`core, utils, helpers, numeric, text, sequences, convert, misc`).
- 모듈마다 함수 3개, 합계 24개. 그중 1개가 버그 함수(대상 과제의 prompt + buggy_solution),
  23개는 교란용으로 다른 과제의 정상 함수(prompt + canonical_solution).
- 교란용 함수는 최상위 함수가 하나인 과제에서만 뽑고, 대상 과제들은 교란용에서 뺀다.
- 버그 함수가 들어갈 모듈과 모듈 안 위치는 seed 로 무작위. 모듈 이름은 함수 내용과 무관하다.
- 각 모듈의 import 문은 맨 위로 모은다. `__init__.py` 는 모든 모듈을 `from .x import *` 로 다시 내보낸다.
- 저장소 루트에 README.md(패키지 설명, 함수 목록 없음)와 setup.cfg 를 둔다.
- 이슈 문장에는 함수 이름과 패키지 이름만 적고 파일 이름은 적지 않는다.
- 숨겨진 테스트는 원본 그대로이며 `from toolkit import <함수>` 로 불러 채점한다.
"""
import argparse
import hashlib
import json
import random
import re
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]
PACKAGE = "toolkit"
MODULES = ["core", "utils", "helpers", "numeric", "text", "sequences", "convert", "misc"]
FUNCS_PER_MODULE = 3
_TOPDEF = re.compile(r"^def (\w+)", re.M)
_IMPORT = re.compile(r"^(?:from \S+ import .+|import .+)$", re.M)


def split_imports(src: str) -> tuple[list[str], str]:
    """함수 원문에서 맨 앞 import 줄들을 떼어 낸다."""
    imports = _IMPORT.findall(src.split("def ", 1)[0])
    body = src
    for line in imports:
        body = body.replace(line + "\n", "", 1)
    return imports, body.strip("\n") + "\n"


def build_repo(target: dict, distractors: list[dict], rng: random.Random) -> tuple[dict, str]:
    slots = [(m, i) for m in MODULES for i in range(FUNCS_PER_MODULE)]
    rng.shuffle(slots)
    target_slot, distractor_slots = slots[0], slots[1:]
    funcs = {target_slot: target["prompt"] + target["buggy_solution"]}
    for slot, d in zip(distractor_slots, distractors):
        funcs[slot] = d["prompt"] + d["canonical_solution"]
    files = {}
    for m in MODULES:
        imports, bodies = [], []
        for i in range(FUNCS_PER_MODULE):
            imp, body = split_imports(funcs[(m, i)])
            imports += [x for x in imp if x not in imports]
            bodies.append(body)
        header = f'"""{PACKAGE}.{m}"""\n' + ("\n".join(imports) + "\n" if imports else "")
        files[f"{PACKAGE}/{m}.py"] = header + "\n\n" + "\n\n".join(bodies)
    files[f"{PACKAGE}/__init__.py"] = (f'"""{PACKAGE}: small utility functions."""\n'
                                       + "".join(f"from .{m} import *  # noqa: F401,F403\n" for m in MODULES))
    files["README.md"] = (f"# {PACKAGE}\n\nA collection of small utility functions grouped into modules:\n"
                          + "".join(f"- `{PACKAGE}/{m}.py`\n" for m in MODULES)
                          + f"\nAll public functions are importable from `{PACKAGE}` directly.\n")
    files["setup.cfg"] = f"[metadata]\nname = {PACKAGE}\nversion = 0.1.0\n\n[options]\npackages = {PACKAGE}\n"
    return files, f"{PACKAGE}/{target_slot[0]}.py"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--targets", required=True, help="대상 과제 목록이 든 tasks.json (prepare_tasks.py 출력)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, required=True)
    args = ap.parse_args()

    import pyarrow.parquet as pq
    src = Path(args.source)
    rows = {r["task_id"]: r for r in pq.read_table(src).to_pylist()}
    targets_doc = json.loads(Path(args.targets).read_text())
    target_ids = [t["source_id"] for t in targets_doc["tasks"]]
    pool = sorted((r for tid, r in rows.items() if tid not in target_ids and len(_TOPDEF.findall(r["prompt"])) == 1),
                  key=lambda r: int(r["task_id"].split("/")[1]))
    n_distractors = len(MODULES) * FUNCS_PER_MODULE - 1

    tasks = []
    for k, tid in enumerate(target_ids):
        r = rows[tid]
        rng = random.Random(args.seed * 1000 + k)
        distractors = rng.sample(pool, n_distractors)
        files, target_file = build_repo(r, distractors, rng)
        tasks.append({
            "task_id": tid.replace("/", "-") + "-wrapped",
            "source_id": tid,
            "issue": (f"Calling `{r['entry_point']}` from the `{PACKAGE}` package does not behave as described in "
                      f"its docstring.\nFix the bug. Keep the function name and signature unchanged."),
            "repo": {"files": files, "target_file": target_file, "package": PACKAGE},
            "hidden_test": {"imports": r["import"], "setup": r["test_setup"], "entry_point": r["entry_point"],
                            "test": r["test"], "import_from": PACKAGE},
            "reference": {"canonical_solution": r["canonical_solution"], "buggy_solution": r["buggy_solution"],
                          "bug_type": r["bug_type"], "target_file": target_file,
                          "distractor_source_ids": [d["task_id"] for d in distractors],
                          "note": "채점과 mock 전용. 에이전트에게 보여 주지 않는다."},
        })
    out = {
        "source": {**targets_doc["source"], "sha256": hashlib.sha256(src.read_bytes()).hexdigest()},
        "selection": {**targets_doc["selection"], "wrapping": {
            "script": "src/wrap_tasks.py", "seed": args.seed, "package": PACKAGE, "modules": MODULES,
            "functions_per_module": FUNCS_PER_MODULE, "distractor_pool_size": len(pool),
            "targets_from": str(Path(args.targets).name)}},
        "tasks": tasks,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    sizes = [sum(len(v) for v in t["repo"]["files"].values()) for t in tasks]
    print(f"{len(tasks)} wrapped tasks -> {args.out} | repo chars min {min(sizes)} max {max(sizes)}")
    for t in tasks:
        print(f"  {t['task_id']:>22}  bug in {t['repo']['target_file']}")


if __name__ == "__main__":
    main()
