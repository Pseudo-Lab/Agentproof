"""결과 폴더의 로그에서 로컬 식별자(레포 경로, 임시 경로, 홈 경로, 사용자명)를 가린다.

사용법 (레포 루트에서):
  python3 experiments/E01-tool-output-compression/src/sanitize_logs.py experiments/E01-tool-output-compression/results/pilot/<run-id>

run.py 는 새 실행의 궤적을 저장할 때 같은 정리를 자동으로 적용한다. 이 스크립트는 그 기능을 넣기 전에
만든 결과에 한 번 적용하기 위한 것이다. 바꾸는 것은 문자열뿐이며 토큰 수·상태·채점 결과는 그대로 둔다.
"""
import argparse
import json
import sys
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(EXPERIMENT / "src"))
from agent_core import local_identifiers, sanitize_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dirs", nargs="+")
    args = ap.parse_args()
    pairs = local_identifiers(ROOT)
    for run_dir in args.run_dirs:
        changed = 0
        for f in sorted(Path(run_dir).rglob("*")):
            if f.suffix not in (".json", ".jsonl") or not f.is_file():
                continue
            text = f.read_text()
            new = sanitize_text(text, pairs)
            if new != text:
                for line in (new.splitlines() if f.suffix == ".jsonl" else [new]):
                    if line.strip():
                        json.loads(line)  # 정리 뒤에도 JSON 이 유효한지 확인
                f.write_text(new)
                changed += 1
        leftover = [old for old, _ in pairs if any(old in p.read_text() for p in Path(run_dir).rglob("*.json*"))]
        print(f"{run_dir}: {changed} files sanitized; leftover identifiers: {leftover or 'none'}")


if __name__ == "__main__":
    main()
