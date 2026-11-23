"""W8 결과표(반복 신뢰성·비용 대비 효과)를 trials.jsonl 에서 다시 계산한다. 모델 호출 없음, 표준 라이브러리만 쓴다.

사용:
  python3 src/w8_table.py results/main/ctx16k-main-002 [results/main/ctx16k-keep10-001 ...] [--repeats 3]

조건별로 출력하는 값:
  - 시도 단위 성공률 (성공 / 시도)
  - 반복 간 편차: 회차별 성공률의 표본 표준편차와 최소~최대
  - pass^k: 1~k 회차를 모두 성공한 과제 수 / 과제 수 (k = --repeats)
  - 입력·출력 토큰 합계, 벽시계 합계(초)
  - 성공 1건당 입력 토큰, 성공 1건당 시간(초). 금액은 로컬 추론이라 null
"""
import argparse
import json
import statistics

from pathlib import Path


def load(run_dir: Path) -> list[dict]:
    with open(run_dir / "trials.jsonl") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(rows: list[dict], repeats: int | None) -> dict:
    reps = sorted({r["repeat_id"] for r in rows})
    if repeats:
        reps = [k for k in reps if k <= repeats]
        rows = [r for r in rows if r["repeat_id"] in reps]
    tasks = sorted({r["task_id"] for r in rows})
    per_rep = []
    for k in reps:
        rk = [r for r in rows if r["repeat_id"] == k]
        per_rep.append(sum(r["status"] == "success" for r in rk) / len(rk))
    all_success = sum(
        all(r["status"] == "success" for r in rows if r["task_id"] == t)
        and len([r for r in rows if r["task_id"] == t]) == len(reps)
        for t in tasks)
    succ = sum(r["status"] == "success" for r in rows)
    in_tok = sum(r["input_tokens"] for r in rows)
    out_tok = sum(r["output_tokens"] for r in rows)
    sec = sum(r["latency_ms"] for r in rows) / 1000
    return {
        "n_trials": len(rows), "n_tasks": len(tasks), "repeats": len(reps),
        "successes": succ, "success_rate": succ / len(rows),
        "per_repeat_success_rate": per_rep,
        "per_repeat_sd": statistics.stdev(per_rep) if len(per_rep) > 1 else None,
        "pass_all_repeats": all_success,
        "input_tokens": in_tok, "output_tokens": out_tok, "wall_seconds": sec,
        "input_tokens_per_success": in_tok / succ if succ else None,
        "seconds_per_success": sec / succ if succ else None,
        "cost_usd": None, "cost_missing_reason": "local inference on own hardware; no per-token price",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--repeats", type=int, help="앞 N 회차만 쓴다 (pass^N)")
    ap.add_argument("--json", help="계산 결과를 이 경로에 JSON 으로 저장")
    args = ap.parse_args()
    out = {}
    for run in args.runs:
        rows = load(Path(run))
        name = Path(run).name
        for cond in sorted({r["condition"] for r in rows}):
            s = summarize([r for r in rows if r["condition"] == cond], args.repeats)
            out[f"{name}/{cond}"] = s
            sd = f"{s['per_repeat_sd'] * 100:.1f}%p" if s["per_repeat_sd"] is not None else "N/A"
            reps = ", ".join(f"{p * 100:.1f}" for p in s["per_repeat_success_rate"])
            ips = f"{s['input_tokens_per_success']:,.0f}" if s["successes"] else "N/A"
            sps = f"{s['seconds_per_success']:,.0f}" if s["successes"] else "N/A"
            print(f"{name}/{cond}: 성공률 {s['success_rate'] * 100:.1f}% ({s['successes']}/{s['n_trials']}), "
                  f"회차별 [{reps}] SD {sd}, pass^{s['repeats']} {s['pass_all_repeats']}/{s['n_tasks']}, "
                  f"입력 {s['input_tokens']:,} / 출력 {s['output_tokens']:,} 토큰, {s['wall_seconds']:,.0f}초, "
                  f"성공당 입력 {ips} 토큰 · {sps}초")
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
