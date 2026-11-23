"""본 실험 사전 고정 분석 (CARD.md "본 실험 사전 고정" 절).

표준 라이브러리만 쓴다.

    python3 src/analyze_main.py results/main/swe-main-001 --repeats 3 --solved-min 2
    python3 src/analyze_main.py results/main/swe-main-001 --repeats 5 --solved-min 3

- 주 분석: 과제 단위 "풀었다"(N회 중 k회 이상 성공)를 a/b 짝지어 McNemar 정확 검정(양측),
  해결률 차이의 과제 부트스트랩 95% 구간(10,000회, seed 20261027).
- 보조: 시도 단위 성공률 차이와 과제 부트스트랩 구간, 과제별 입력 토큰·시간 상대차이
  (과제 안 평균끼리 (b-a)/a, 중앙값, 중앙값 부트스트랩 구간, Wilcoxon 부호순위 정확 검정),
  같은 과제·회차 짝 불일치 McNemar(참고).
"""
import argparse
import json
import random
from collections import defaultdict
from math import comb
from pathlib import Path
from statistics import mean, median

B = 10_000
SEED = 20261027


def mcnemar_exact(n01: int, n10: int) -> float:
    n = n01 + n10
    if n == 0:
        return 1.0
    k = min(n01, n10)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def wilcoxon_exact(diffs: list[float]) -> float:
    """양측 정확 검정. 0 은 버리고 동순위는 평균 순위(반올림 없이 2배 정수로 계산)."""
    d = [x for x in diffs if x != 0]
    n = len(d)
    if n == 0:
        return 1.0
    order = sorted(range(n), key=lambda i: abs(d[i]))
    ranks2 = [0] * n  # 순위의 2배
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(d[order[j + 1]]) == abs(d[order[i]]):
            j += 1
        for t in range(i, j + 1):
            ranks2[order[t]] = i + j + 2
        i = j + 1
    w_plus = sum(r for r, x in zip(ranks2, d) if x > 0)
    total = sum(ranks2)
    dist = defaultdict(int)  # 부호 2^n 조합에 대한 W+ 분포
    dist[0] = 1
    for r in ranks2:
        nxt = defaultdict(int)
        for s, c in dist.items():
            nxt[s] += c
            nxt[s + r] += c
        dist = nxt
    lo = min(w_plus, total - w_plus)
    p = 2 * sum(c for s, c in dist.items() if s <= lo) / 2 ** n
    return min(1.0, p)


def boot_ci(tasks, stat, rng):
    vals = sorted(stat([rng.choice(tasks) for _ in tasks]) for _ in range(B))
    return vals[int(0.025 * B)], vals[int(0.975 * B) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--repeats", type=int, required=True, help="앞에서부터 이 회차까지만 쓴다")
    ap.add_argument("--solved-min", type=int, required=True, help="'풀었다' 의 최소 성공 회차 수")
    ap.add_argument("--out", help="결과 JSON 경로")
    args = ap.parse_args()

    rows = [json.loads(l) for l in (Path(args.run_dir) / "trials.jsonl").read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["repeat_id"] <= args.repeats]
    cell = defaultdict(list)
    for r in rows:
        cell[(r["task_id"], r["condition"])].append(r)
    tasks = sorted({r["task_id"] for r in rows})
    for t in tasks:
        for c in ("baseline", "intervention"):
            got = sorted(r["repeat_id"] for r in cell[(t, c)])
            if got != list(range(1, args.repeats + 1)):
                raise SystemExit(f"불완전: {t} {c} 회차 {got}")
    if any(r["status"] == "error" for r in rows):
        raise SystemExit("status=error 행이 있다")

    succ = {k: sum(r["status"] == "success" for r in v) for k, v in cell.items()}
    solved = {k: s >= args.solved_min for k, s in succ.items()}
    both = sum(solved[(t, "baseline")] and solved[(t, "intervention")] for t in tasks)
    a_only = sum(solved[(t, "baseline")] and not solved[(t, "intervention")] for t in tasks)
    b_only = sum(not solved[(t, "baseline")] and solved[(t, "intervention")] for t in tasks)
    neither = len(tasks) - both - a_only - b_only

    rng = random.Random(SEED)
    solved_diff = lambda ts: (sum(solved[(t, "intervention")] for t in ts) - sum(solved[(t, "baseline")] for t in ts)) / len(ts)
    attempt_diff = lambda ts: (sum(succ[(t, "intervention")] for t in ts) - sum(succ[(t, "baseline")] for t in ts)) / (len(ts) * args.repeats)

    def rel(field):
        out = {}
        for t in tasks:
            a = mean(r[field] for r in cell[(t, "baseline")])
            b = mean(r[field] for r in cell[(t, "intervention")])
            out[t] = (b - a) / a
        return out

    pair_a = pair_b = 0
    for t in tasks:
        ra = {r["repeat_id"]: r["status"] == "success" for r in cell[(t, "baseline")]}
        rb = {r["repeat_id"]: r["status"] == "success" for r in cell[(t, "intervention")]}
        for k in ra:
            pair_a += ra[k] and not rb[k]
            pair_b += rb[k] and not ra[k]

    res = {
        "run_dir": args.run_dir, "repeats": args.repeats, "solved_min": args.solved_min, "n_tasks": len(tasks),
        "bootstrap": {"B": B, "seed": SEED, "unit": "task"},
        "primary": {
            "solved_baseline": sum(solved[(t, "baseline")] for t in tasks),
            "solved_intervention": sum(solved[(t, "intervention")] for t in tasks),
            "a_only": a_only, "b_only": b_only, "both": both, "neither": neither,
            "mcnemar_exact_p": mcnemar_exact(a_only, b_only),
            "diff_b_minus_a": solved_diff(tasks), "diff_ci95": boot_ci(tasks, solved_diff, rng),
        },
        "attempt_level": {
            "success_baseline": sum(succ[(t, "baseline")] for t in tasks),
            "success_intervention": sum(succ[(t, "intervention")] for t in tasks),
            "attempts_per_condition": len(tasks) * args.repeats,
            "diff_b_minus_a": attempt_diff(tasks), "diff_ci95": boot_ci(tasks, attempt_diff, rng),
            "paired_a_only": pair_a, "paired_b_only": pair_b, "paired_mcnemar_p_reference_only": mcnemar_exact(pair_a, pair_b),
        },
    }
    for name, field in (("input_tokens", "input_tokens"), ("latency", "latency_ms")):
        d = rel(field)
        res[name] = {
            "relative_diff_median": median(d.values()), "relative_diff_mean": mean(d.values()),
            "median_ci95": boot_ci(tasks, lambda ts: median(d[t] for t in ts), rng),
            "wilcoxon_exact_p": wilcoxon_exact(list(d.values())),
            "tasks_b_lower": sum(v < 0 for v in d.values()),
        }
    res["per_task"] = {t: {"baseline": succ[(t, "baseline")], "intervention": succ[(t, "intervention")]} for t in tasks}
    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
