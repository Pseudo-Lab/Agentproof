"""결과 파일과 알고리즘 간 비교표.

results/<benchmark>/<algorithm>/<run_id>/
    manifest.json     설정·데이터 해시·어댑터 setup() 반환값·패키지 버전
    records.jsonl     문항별: 질문·정답·예측·검색 결과·지표·시간·토큰
    summary.json      aggregate() 결과 (모든 알고리즘이 같은 스키마)
    summary.md        사람이 읽는 표
    adapter.log       알고리즘 작업 프로세스 stderr

python run.py --compare results/locomo   → 같은 벤치마크의 summary.json 들을 한 표로 모은다.
"""

from __future__ import annotations

from pathlib import Path


def write_summary(run_dir: Path, summary: dict) -> None:
    raise NotImplementedError("TODO")


def compare(benchmark_dir: Path) -> str:
    raise NotImplementedError("TODO: 알고리즘 × (overall, 카테고리별, 효율, 비용) 마크다운 표")
