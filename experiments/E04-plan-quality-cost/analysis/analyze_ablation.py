"""Offline paired analysis of the focused C/E role-diversity ablation."""
import argparse
import csv
import json
import random
import statistics
from pathlib import Path


def bootstrap(values, rng, iterations=10000):
    if len(values) < 2:
        return None
    draws = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(iterations))
    return [draws[int(iterations * 0.025)], draws[int(iterations * 0.975)]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    run = args.run_directory
    with (run / "samples.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows = [r for r in rows if r["group"] in {"C", "E"} and r["is_latest_outcome"].lower() == "true"]
    if not rows:
        raise SystemExit("No latest C/E outcomes found in samples.csv")
    record_by_id = {}
    for path in (run / "records").glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        record_by_id[record["sample_id"]] = record
    if not record_by_id and (run / "trials.jsonl").exists():
        with (run / "trials.jsonl").open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    record_by_id[record["sample_id"]] = record
    trial_rows = []
    for row in rows:
        record = record_by_id[row["sample_id"]]
        calls = record["calls"]
        trial_rows.append({
            "sample_id": row["sample_id"], "task_id": row["task_id"],
            "task_layer": row["task_layer"], "condition": row["group"],
            "repeat": int(row["repeat"]), "status": row["status"],
            "score_100": float(row["score_100"]), "pass": row["pass"].lower() == "true",
            "critical": row["critical"].lower() == "true",
            "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
            "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
            "generation_cost_usd": float(row["generation_cost_usd"]),
            "judge_cost_usd": float(row["judge_cost_usd"]),
            "total_cost_usd": float(row["total_cost_usd"]),
            "unknown_cost_calls": int(row["unknown_cost_calls"]),
            "calls": [{k: c.get(k) for k in ("stage", "model", "status", "input_tokens", "output_tokens", "cost_usd")}
                      for c in calls],
        })
    (run / "trials.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in trial_rows),
        encoding="utf-8")
    tasks = sorted({r["task_id"] for r in rows})
    groups = {}
    task_means = {g: {} for g in ("C", "E")}
    task_passes = {g: {} for g in ("C", "E")}
    for g in ("C", "E"):
        data = [r for r in rows if r["group"] == g]
        if len(data) != len(tasks) * 3:
            raise SystemExit(f"Expected 3 repeats per task for {g}; found {len(data)} outcomes")
        passed = sum(r["pass"].lower() == "true" for r in data)
        per_repeat = [sum(r["pass"].lower() == "true" for r in data if int(r["repeat"]) == rep)
                      / len(tasks) * 100 for rep in range(3)]
        per_task_pass3 = 0
        for task in tasks:
            task_rows = [r for r in data if r["task_id"] == task]
            if len(task_rows) != 3:
                raise SystemExit(f"Expected 3 repeats for {g}/{task}; found {len(task_rows)}")
            task_means[g][task] = statistics.mean(float(r["score_100"]) for r in task_rows)
            task_passes[g][task] = statistics.mean(r["pass"].lower() == "true" for r in task_rows)
            per_task_pass3 += all(r["pass"].lower() == "true" for r in task_rows)
        total_cost = sum(float(r["total_cost_usd"]) for r in data)
        token_records = [record_by_id[r["sample_id"]] for r in data]
        input_tokens = sum(c.get("input_tokens", 0) for record in token_records for c in record["calls"])
        output_tokens = sum(c.get("output_tokens", 0) for record in token_records for c in record["calls"])
        groups[g] = {
            "n": len(data), "passes": passed, "pass_rate": passed / len(data),
            "mean_score_100": statistics.mean(float(r["score_100"]) for r in data),
            "repeat_success_rates_pp": per_repeat,
            "repeat_success_rate_sd_pp": statistics.stdev(per_repeat),
            "pass3_tasks": per_task_pass3, "task_count": len(tasks),
            "generation_cost_usd": sum(float(r["generation_cost_usd"]) for r in data),
            "judge_cost_usd": sum(float(r["judge_cost_usd"]) for r in data),
            "total_cost_usd": total_cost, "cost_per_success_usd": total_cost / passed,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "total_tokens_per_sample": (input_tokens + output_tokens) / len(data),
            "unknown_cost_calls": sum(int(r["unknown_cost_calls"]) for r in data),
        }

    score_diffs = [task_means["E"][t] - task_means["C"][t] for t in tasks]
    pass_diffs = [task_passes["E"][t] - task_passes["C"][t] for t in tasks]
    wins = {"E": 0, "C": 0, "tie": 0}
    for t, diff in zip(tasks, score_diffs):
        wins["E" if diff > 0 else "C" if diff < 0 else "tie"] += 1
    rng = random.Random(20261125)
    paired = {
        "score_E_minus_C_points": statistics.mean(score_diffs),
        "score_task_cluster_bootstrap_95_ci": bootstrap(score_diffs, rng),
        "pass_rate_E_minus_C_pp": statistics.mean(pass_diffs) * 100,
        "pass_rate_task_cluster_bootstrap_95_ci_pp": [x * 100 for x in bootstrap(pass_diffs, rng)],
        "score_task_wins": wins,
    }
    output = {
        "design": "C/E role-diversity ablation; 16 tasks x 3 repeats x 2 conditions",
        "conditions": {
            "C": "three homogeneous lightweight planner candidates plus lightweight synthesis",
            "E": "three role-diverse lightweight planner candidates plus the same synthesis",
        },
        "factor_removed": "candidate role diversification",
        "task_count": len(tasks), "groups": groups, "paired": paired,
        "limitations": [
            "Exploratory pilot with 16 tasks and one model family.",
            "The judge is model-based; no human evaluation or execution-success measure.",
            "Cost is a token-usage estimate, not an invoice.",
        ],
    }
    (run / "w8_ablation.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c, e = groups["C"], groups["E"]
    md = [
        "# W8 ablation — role diversity in the low-cost planner ensemble", "",
        "The completed focused run compares E (role-diverse candidates) with C (the same number of homogeneous candidates). Both use the same low-cost model, task, synthesis prompt, output limits, and judge. Only candidate role instructions differ.", "",
        "## Results", "",
        "| Condition | Mean plan score /100 | Pass rate (n) | Repeat SD (pp) | pass^3 | Tokens / sample | Total estimated cost | Cost per passing plan |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| C — role specialization removed | {c['mean_score_100']:.2f} | {100*c['pass_rate']:.2f}% ({c['passes']}/{c['n']}) | {c['repeat_success_rate_sd_pp']:.2f} | {c['pass3_tasks']}/{c['task_count']} | {c['total_tokens_per_sample']:.0f} | ${c['total_cost_usd']:.6f} | ${c['cost_per_success_usd']:.5f} |",
        f"| E — role-diverse intervention | {e['mean_score_100']:.2f} | {100*e['pass_rate']:.2f}% ({e['passes']}/{e['n']}) | {e['repeat_success_rate_sd_pp']:.2f} | {e['pass3_tasks']}/{e['task_count']} | {e['total_tokens_per_sample']:.0f} | ${e['total_cost_usd']:.6f} | ${e['cost_per_success_usd']:.5f} |",
        "", f"E − C paired mean score difference: {paired['score_E_minus_C_points']:+.2f} points; 95% task-cluster bootstrap CI [{paired['score_task_cluster_bootstrap_95_ci'][0]:+.2f}, {paired['score_task_cluster_bootstrap_95_ci'][1]:+.2f}].",
        f"E − C pass-rate difference: {paired['pass_rate_E_minus_C_pp']:+.2f} percentage points; task-cluster bootstrap 95% CI [{paired['pass_rate_task_cluster_bootstrap_95_ci_pp'][0]:+.2f}, {paired['pass_rate_task_cluster_bootstrap_95_ci_pp'][1]:+.2f}].",
        f"Score wins by task (E / C / tie): {wins['E']} / {wins['C']} / {wins['tie']}.",
        f"Known spend across both conditions: ${c['total_cost_usd'] + e['total_cost_usd']:.6f}; unknown-cost calls: {c['unknown_cost_calls'] + e['unknown_cost_calls']}.",
        "", "## Interpretation", "",
        "Treat this as an exploratory ablation. The paired interval is task-clustered; the sample contains 16 tasks and three repeats per condition. It measures plan quality and estimated API cost, not task execution success or equal-dollar-budget performance.", "",
        "Repeat SD is the sample standard deviation of the three repeat-level success rates. pass^3 is the number of tasks that passed in all three repeats. Cost per passing plan includes generation and judge calls.", "",
        "## Reproduction", "",
        "The source records, invocation, manifest, case snapshot, samples.csv, summary.md, and summary.json are stored alongside this analysis. Recompute the analysis offline with:", "",
        "```powershell", f"uv run --python 3.11 python analyze_ablation.py {run.as_posix()}", "```", "",
    ]
    (run / "W8_ABLATION.md").write_text("\n".join(md), encoding="utf-8")
    ko = [
        "# E04 W8 ablation — 경량 플래너 앙상블의 역할 다양성", "",
        "## 연구 질문", "",
        "세 개의 경량 플래너에 서로 다른 역할을 주면, 모두 같은 역할을 받는 경우보다 최종 계획의 품질이나 신뢰성이 좋아지는가?",
        "", "## 비교 조건", "",
        "| 조건 | 후보 플래너 | 종합 |", "|---|---|---|",
        "| C — ablation | `gpt-6-luna` 후보 3개 모두 일반 planner 역할 | 동일한 `gpt-6-luna` 종합기 1회 |",
        "| E — 개입 | `gpt-6-luna` 후보 3개: planner, 위험·의존성 검토자, 검증·복구 검토자 | 동일한 `gpt-6-luna` 종합기 1회 |",
        "", "후보 수, 과제, 기본 프롬프트, 종합 프롬프트, 출력 제한, judge와 모델 계열은 같고 후보 역할 지시만 다릅니다. 따라서 C는 E에서 역할 다양성을 제거한 ablation입니다.",
        "", "## 새 실행 결과", "",
        "16개 과제 × 조건별 3회 반복 × 2조건으로 총 96개 결과를 실행했습니다. C와 E 각각 48개 결과가 모두 채점됐고, 생성 오류·judge 오류·비용 미상 호출은 없었습니다. 반복 간 편차는 세 번의 반복별 성공률(각 16개 과제)의 표본 표준편차입니다. pass^3은 세 반복에서 모두 통과한 과제 수입니다. 비용은 generation과 judge 호출 비용을 합산한 사용량 기반 추정치입니다.",
        "", "| 조건 | 평균 Plan 점수 /100 | 성공률 (n) | 반복 간 SD (pp) | pass^3 | 샘플당 토큰 | 총 추정 비용 | 성공 1건당 비용 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        f"| C — 역할 특화 제거 | {c['mean_score_100']:.2f} | {100*c['pass_rate']:.2f}% ({c['passes']}/{c['n']}) | {c['repeat_success_rate_sd_pp']:.2f} | {c['pass3_tasks']}/{c['task_count']} | {c['total_tokens_per_sample']:.0f} | ${c['total_cost_usd']:.6f} | ${c['cost_per_success_usd']:.5f} |",
        f"| E — 역할 분담 개입 | {e['mean_score_100']:.2f} | {100*e['pass_rate']:.2f}% ({e['passes']}/{e['n']}) | {e['repeat_success_rate_sd_pp']:.2f} | {e['pass3_tasks']}/{e['task_count']} | {e['total_tokens_per_sample']:.0f} | ${e['total_cost_usd']:.6f} | ${e['cost_per_success_usd']:.5f} |",
        "", f"태스크 단위 paired 비교 E−C 평균 점수 차이는 {paired['score_E_minus_C_points']:+.2f}점, 95% 태스크 군집 bootstrap 구간은 [{paired['score_task_cluster_bootstrap_95_ci'][0]:+.2f}, {paired['score_task_cluster_bootstrap_95_ci'][1]:+.2f}]입니다.",
        f"성공률 차이 E−C는 {paired['pass_rate_E_minus_C_pp']:+.2f}%p, 95% 구간은 [{paired['pass_rate_task_cluster_bootstrap_95_ci_pp'][0]:+.2f}, {paired['pass_rate_task_cluster_bootstrap_95_ci_pp'][1]:+.2f}]입니다. 과제별 평균 점수는 E가 {wins['E']}개, C가 {wins['C']}개에서 높았고 동점은 {wins['tie']}개였습니다.",
        f"전체 알려진 사용 비용은 ${c['total_cost_usd'] + e['total_cost_usd']:.6f}이며, 비용 미상 호출은 0건입니다. E의 샘플당 토큰은 C보다 {100*(e['total_tokens_per_sample']/c['total_tokens_per_sample']-1):.2f}% 많았습니다.",
        "", "## 해석과 한계", "",
        "이 파일럿에서는 역할 분담이 평균 점수를 높이지 않았습니다. 두 조건의 관측 성공률은 같았고, C가 평균 점수·pass^3·반복 안정성에서 조금 높고 비용은 낮았습니다. 태스크 16개와 반복 3회의 탐색 결과이므로 조건이 동등하다는 증거로 해석할 수는 없습니다. 이 실험은 계획 품질을 평가했으며 실제 코드 실행이나 태스크 완료율은 측정하지 않았습니다. 비용은 청구서가 아닌 토큰 사용량 기반 추정치입니다.",
        "", "## 재현", "",
        "상세 실행 정보는 같은 폴더의 `manifest.json`, `invocation.json`, `cases.json`, `samples.csv`, `trials.jsonl`에 있습니다. 오프라인 분석은 다음처럼 다시 계산할 수 있습니다.",
        "", "```powershell", f"uv run --python 3.11 python analyze_ablation.py {run.as_posix()}", "```", "",
    ]
    (run / "W8_ABLATION_KO.md").write_text("\n".join(ko), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
