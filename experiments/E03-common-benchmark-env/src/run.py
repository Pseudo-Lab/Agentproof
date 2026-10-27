"""평가 진입점.

    .venv/bin/python run.py --algorithm example --benchmark locomo
    .venv/bin/python run.py --algorithm idea1 --benchmark longmemeval --eval-metric LLM-as-a-judge F1
    .venv/bin/python run.py --algorithm example --benchmark locomo --dry-run   # 설정·출력 규격만 확인
    .venv/bin/python run.py --list
    .venv/bin/python run.py --compare ../results/pilot/locomo

공통 평가 환경(이 파일)은 src/.venv 에서, 알고리즘은 algorithms/<name>/.venv 에서 따로 돈다.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from benchmarks import BENCHMARKS  # noqa: E402
from harness.metrics import EVAL_METRICS  # noqa: E402
from harness.registry import algorithms  # noqa: E402

METRIC_ALIASES = {"f1": "f1", "bleu": "bleu1", "bleu1": "bleu1", "bleu-1": "bleu1", "blue": "bleu1",
                  "llm_judge": "llm_judge", "llm-judge": "llm_judge", "llm-as-a-judge": "llm_judge",
                  "judge": "llm_judge"}


def metric_name(value: str) -> str:
    try:
        return METRIC_ALIASES[value.lower()]
    except KeyError:
        raise argparse.ArgumentTypeError(f"지표는 {', '.join(EVAL_METRICS)} 중 하나 (별칭: F1, BLEU, LLM-as-a-judge)")


def algorithm_name(value: str) -> str:
    """my-idea, My_Idea, MyIdea → myidea"""
    return value.lower().replace("-", "").replace("_", "")


def positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("1 이상의 정수가 필요하다")
    return n


def parse_args(argv=None):
    algos = algorithms()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--algorithm", type=algorithm_name, choices=sorted(algos))
    ap.add_argument("--benchmark", choices=sorted(BENCHMARKS))
    ap.add_argument("--variant", help="데이터 변형 (기본: 벤치마크의 첫 변형, --list 참고)")
    ap.add_argument("--dataset", type=Path, help="원본 JSON 경로 (기본: 변형에 맞는 저장소 내 경로)")
    ap.add_argument("--eval-metric", "--eval_metric", dest="eval_metrics", type=metric_name, nargs="+",
                    action="append", metavar="METRIC",
                    help="정답 지표: F1, BLEU(blue), LLM-as-a-judge. 여러 값·옵션 반복 가능. 기본: 전부."
                         " 효율·비용 지표는 항상 기록")
    ap.add_argument("--answer-mode", choices=("harness", "native"), default="harness",
                    help="harness: 공통 답변기(통일 비교) / native: 알고리즘 고유 답변기")
    ap.add_argument("--answer-model", default="gpt-4o-mini")
    ap.add_argument("--judge-model", help="기본: 벤치마크 원본 평가 모델 (--list 참고)")
    ap.add_argument("--top-k", type=positive, default=10, help="질문당 검색 결과 수. 모든 알고리즘에 같은 값")
    ap.add_argument("--algorithm-python", type=Path, help="algorithm.toml 대신 쓸 알고리즘 venv 의 python 경로")
    ap.add_argument("--workers", type=positive, default=4, help="알고리즘 작업 프로세스 수 (에피소드 단위 병렬)")
    ap.add_argument("--limit-episodes", type=int, default=0, help="앞에서부터 N개 에피소드만 (0 = 전체)")
    ap.add_argument("--max-questions", type=int, default=0, help="에피소드당 문항 상한 (0 = 전체)")
    ap.add_argument("--repeats", type=positive, default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fake", action="store_true", help="과금 없는 배선 점검 (점수 무의미)")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--output-dir", type=Path, default=ROOT.parent / "results" / "pilot")
    ap.add_argument("--dry-run", action="store_true", help="실행 계획·출력 규격을 JSON 으로 출력. 파일·API·설치 없음")
    ap.add_argument("--list", action="store_true", help="등록된 알고리즘(venv 상태)·벤치마크·지표")
    ap.add_argument("--compare", type=Path, help="results/<benchmark> 의 결과들을 한 표로")
    args = ap.parse_args(argv)
    if args.list or args.compare:
        return args
    if not (args.algorithm and args.benchmark):
        ap.error("--algorithm 과 --benchmark 가 필요하다 (또는 --list / --compare)")
    bench = BENCHMARKS[args.benchmark]
    args.variant = args.variant or bench.variants[0]
    if args.variant not in bench.variants:
        ap.error(f"{args.benchmark} 변형은 {', '.join(bench.variants)} 중 하나")
    args.eval_metrics = (list(dict.fromkeys(m for batch in args.eval_metrics for m in batch))
                         if args.eval_metrics else list(EVAL_METRICS))
    if args.answer_mode == "native" and "native_answer" not in algos[args.algorithm].capabilities:
        ap.error(f"{args.algorithm} 은 native 답변을 지원하지 않는다")
    return args


def print_list() -> None:
    print("알고리즘")
    for name, spec in algorithms().items():
        state = "준비됨" if spec.python.exists() else f"venv 없음 → scripts/setup_venv.sh {name}"
        print(f"  {name:10s} py{spec.python_version}  {state}\n             {spec.description}")
    print("벤치마크")
    for name, bench in BENCHMARKS.items():
        print(f"  {name:12s} scope={bench.scope_unit:12s} judge 기본 {bench.default_judge_model}\n"
              f"               변형 {', '.join(bench.variants)}")
    print(f"지표\n  {', '.join(EVAL_METRICS)}  (+ 효율·비용 항상)")


def dry_run(cfg, spec, bench) -> dict:
    python = cfg.algorithm_python or spec.python
    dataset = cfg.dataset or bench.dataset_path(cfg.variant)
    return {
        "status": "planned",
        "config": asdict(cfg),
        "algorithm": {"name": spec.name, "adapter": spec.adapter, "python": str(python),
                      "python_exists": Path(python).is_file(), "capabilities": spec.capabilities,
                      "config": spec.config},
        "benchmark": {"name": bench.name, "scope_unit": bench.scope_unit, "dataset": str(dataset),
                      "dataset_exists": Path(dataset).is_file(), "categories": bench.categories,
                      "excluded_categories": list(bench.excluded_categories),
                      "judge_model": cfg.judge_model or bench.default_judge_model},
        "metric_protocol": {
            "scale": "0..1 (표에서는 %)",
            "f1": "set(simple_tokenize) — mem0-evaluation utils.py",
            "bleu1": "nltk word_tokenize + sentence_bleu(weights=(1,0,0,0), method1)",
            "llm_judge": "이진, 벤치마크별 원본 rubric, 모든 알고리즘에 같은 judge 모델"},
        "output": str(cfg.output_dir / cfg.benchmark / cfg.algorithm / "<run_id>"),
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list:
        print_list()
        return 0
    if args.compare:
        from harness.report import compare
        print(compare(args.compare))
        return 0
    from harness.runner import RunConfig, run
    spec, bench = algorithms()[args.algorithm], BENCHMARKS[args.benchmark]
    cfg = RunConfig(algorithm=args.algorithm, benchmark=args.benchmark, variant=args.variant,
                    eval_metrics=args.eval_metrics,
                    dataset=args.dataset.resolve() if args.dataset else None,
                    algorithm_python=args.algorithm_python.absolute() if args.algorithm_python else None,
                    seed=args.seed, answer_mode=args.answer_mode, answer_model=args.answer_model,
                    judge_model=args.judge_model, top_k=args.top_k, workers=args.workers,
                    limit_episodes=args.limit_episodes, max_questions=args.max_questions,
                    repeats=args.repeats, fake=args.fake, resume=args.resume,
                    output_dir=args.output_dir.resolve())
    if args.dry_run:
        print(json.dumps(dry_run(cfg, spec, bench), ensure_ascii=False, indent=2, default=str))
        return 0
    try:
        return run(cfg)
    except NotImplementedError as exc:
        print(f"아직 뼈대 단계다 ({exc}). --dry-run 으로 설정을 확인하고, 구현 순서는 README.md §6.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
