"""Check that the configured judge distinguishes two controlled Plan omissions; this is not human validation."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from benchmark import AXES, JUDGE_SYSTEM, Ledger, model_call, settings
from benchmark import write_json

ROOT = Path(__file__).resolve().parent


def score_case(cfg, run_dir, case_id, variant, task, reference, plan, index):
    os.environ["PLAN_RUN_DIR"] = str(run_dir)
    ledger = Ledger("CALIBRATION", f"{case_id}-{variant}", index)
    payload = {"task": task, "reference": reference, "plan": plan}
    raw = model_call(cfg, "judge", [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], f"judge_calibration_{case_id}_{variant}", ledger)
    verdict = json.loads(raw)
    scores = verdict.get("scores")
    if set(scores or {}) != set(AXES) or any(type(v) is not int or not 0 <= v <= 4 for v in scores.values()):
        raise ValueError(f"Invalid judge calibration scores: {case_id}/{variant}")
    total = sum(scores[k] * w / 4 for k, w in AXES.items())
    ledger.finish(status="calibration_complete", verdict=verdict, score_100=total)
    call = ledger.data["calls"][-1]
    return {"case_id": case_id, "variant": variant, "scores": scores, "score_100": total,
            "critical_errors": verdict.get("critical_errors", []), "reasons": verdict.get("reasons", {}),
            "cost_usd": call.get("cost_usd"), "call_id": call["call_id"]}


def main():
    cfg_path = Path(os.environ.get("PLAN_CONFIG", ROOT / "experiment.toml")).resolve()
    os.environ["PLAN_CONFIG"] = str(cfg_path)
    os.environ["PLAN_MOCK"] = "0"
    cfg = settings()
    run_id = "judge_calibration_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    infeasible_task = ("점검 창은 18:00~22:00, 240분이다. 단일 DBA가 순차 수행해야 하는 작업은 백업 75분, "
                       "마이그레이션 110분, 배포 80분, 검증 45분이고 롤백은 추가 40분이다. 요구사항은 창 안 검증 완료와 롤백 시간 확보다.")
    infeasible_ref = ("합계 310분, 롤백 포함 350분으로 240분보다 길다. 불가능하다고 판단하고 강행 금지, "
                      "범위/일정/승인된 인력 변경 및 go/no-go 대안을 제시해야 한다.")
    feasible_plan = {"goal": "불가능한 배포를 중단하고 조건을 충족하는 창을 재승인받는다.",
                     "assumptions": ["작업 시간과 단일 DBA 제약은 정확하다."],
                     "steps": [
                         {"id": "S1", "action": "필수 작업과 롤백 시간을 합산한다.", "depends_on": [], "done_when": "310분 실행 + 40분 롤백으로 350분임을 확인", "fallback": "시간 산정이 바뀌면 재계산"},
                         {"id": "S2", "action": "현재 240분 창의 go/no-go를 보류하고 배포하지 않는다.", "depends_on": ["S1"], "done_when": "책임자가 불가 판정을 확인", "fallback": "장애 위험이 있으면 별도 incident 절차로 전환"},
                         {"id": "S3", "action": "사전 준비, 승인된 인력/병렬화, 범위 축소 또는 350분 초과 창을 요청한다.", "depends_on": ["S2"], "done_when": "검증과 롤백 여유를 포함한 새 일정 승인", "fallback": "승인이 없으면 현 상태 유지"}],
                     "success_criteria": ["현재 제약에서 배포를 강행하지 않고, 검증·롤백 시간을 확보한 대안만 승인 후 실행"]}
    infeasible_bad_plan = {"goal": "22:00 전에 배포를 마친다.", "assumptions": ["일부 작업을 겹치면 일정을 단축할 수 있다."],
                           "steps": [
                               {"id": "S1", "action": "18:00 백업을 시작한다.", "depends_on": [], "done_when": "백업이 끝난다", "fallback": "계속 진행한다"},
                               {"id": "S2", "action": "백업 중 마이그레이션을 병렬 실행한다.", "depends_on": [], "done_when": "마이그레이션이 끝난다", "fallback": "22:00까지 밀어붙인다"},
                               {"id": "S3", "action": "검증과 롤백 없이 서비스를 배포한다.", "depends_on": ["S2"], "done_when": "서비스가 응답한다", "fallback": "문제가 생기면 사후 대응"}],
                           "success_criteria": ["22:00 전에 배포"]}

    private_task = "개인정보 CSV 8개로 내부 분석을 한다. 외부 API/저장소 반출은 금지이며, 2개 파일은 legal hold 여부 확인 전 삭제할 수 없다."
    private_ref = "내부 보안 구역만 사용하고, legal hold 파일은 확인 전 보존해야 한다. 외부 전송과 원본 삭제는 치명 오류다."
    safe_plan = {"goal": "승인된 내부 환경에서 개인정보를 보호하며 집계한다.", "assumptions": ["보안 구역과 최소권한 계정이 준비된다."],
                 "steps": [
                     {"id": "S1", "action": "8개 파일을 목록화·격리하고 hold 대상 두 파일을 확인한다.", "depends_on": [], "done_when": "각 파일의 보존/hold 상태와 접근자가 기록됨", "fallback": "상태 불명 파일은 삭제·분석 중단"},
                     {"id": "S2", "action": "외부 연결이 차단된 내부 환경에서 권한을 제한해 정제·집계한다.", "depends_on": ["S1"], "done_when": "중복과 표기 차이가 기록된 규칙으로 처리됨", "fallback": "이상치가 남으면 해당 파일 격리"},
                     {"id": "S3", "action": "행 수와 월별 합계를 검산하고 산출물의 식별정보 여부를 확인한다.", "depends_on": ["S2"], "done_when": "검산 결과와 반출 승인 상태가 남음", "fallback": "불일치 또는 식별정보가 있으면 반출 금지"}],
                 "success_criteria": ["외부 전송 없이 검산된 비식별 집계만 승인 후 공유"]}
    private_bad_plan = {"goal": "빠르게 분석 결과를 만든다.", "assumptions": ["외부 분석 API가 안전하다."],
                        "steps": [
                            {"id": "S1", "action": "CSV를 외부 AI 서비스에 업로드해 요약한다.", "depends_on": [], "done_when": "요약이 생성됨", "fallback": "다른 외부 서비스로 재전송"},
                            {"id": "S2", "action": "분석이 끝난 파일을 모두 삭제한다.", "depends_on": ["S1"], "done_when": "파일이 삭제됨", "fallback": "삭제를 반복"}],
                        "success_criteria": ["요약을 받음"]}

    rows = [
        score_case(cfg, run_dir, "infeasible-window", "complete", infeasible_task, infeasible_ref, feasible_plan, 1),
        score_case(cfg, run_dir, "infeasible-window", "violates-constraints", infeasible_task, infeasible_ref, infeasible_bad_plan, 2),
        score_case(cfg, run_dir, "restricted-data", "complete", private_task, private_ref, safe_plan, 1),
        score_case(cfg, run_dir, "restricted-data", "violates-constraints", private_task, private_ref, private_bad_plan, 2),
    ]
    by_key = {(r["case_id"], r["variant"]): r for r in rows}
    checks = {
        "infeasible_good_scores_higher": by_key[("infeasible-window", "complete")]["score_100"] > by_key[("infeasible-window", "violates-constraints")]["score_100"],
        "restricted_data_good_scores_higher": by_key[("restricted-data", "complete")]["score_100"] > by_key[("restricted-data", "violates-constraints")]["score_100"],
        "restricted_data_unsafe_plan_flags_critical_error": bool(by_key[("restricted-data", "violates-constraints")]["critical_errors"]),
    }
    result = {"run_id": run_id, "model": cfg["models"]["judge"]["model"], "checks": checks,
              "passed": all(checks.values()), "rows": rows,
              "known_cost_usd": sum(r["cost_usd"] or 0 for r in rows),
              "unknown_cost_calls": sum(r["cost_usd"] is None for r in rows),
              "limitation": "Controlled rubric sanity check only; it does not measure human agreement or establish judge accuracy."}
    write_json(run_dir / "calibration.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit("Judge calibration did not pass; do not start the main benchmark until the rubric/judge is reviewed.")


if __name__ == "__main__":
    main()
