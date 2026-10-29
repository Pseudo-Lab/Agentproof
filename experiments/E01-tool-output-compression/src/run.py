"""E01 실행기: mini-swe-agent(2.4.6) 위에서 과제 × 조건 × 반복을 돌리고
AgentProof 규격의 manifest / trials.jsonl / summary.json 을 쓴다.

모델 호출은 --mode real 에서만 일어난다(litellm → Ollama). --mode mock 은 고정 응답으로 경로만 검증한다.
실행 순서: 반복 회차 → 과제 → (baseline, intervention) 교차. 같은 run-id 는 --resume 없이는 덮어쓰지 않는다.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MSWEA_SILENT_STARTUP", "1")
os.environ.setdefault("MSWEA_COST_TRACKING", "ignore_errors")

EXPERIMENT = Path(__file__).resolve().parents[1]
ROOT = EXPERIMENT.parents[1]
sys.path.insert(0, str(EXPERIMENT / "src"))
sys.path.insert(0, str(ROOT / "harness"))

import yaml  # noqa: E402  (mini-swe-agent 의존성)
from minisweagent import __version__ as MINI_VERSION, package_dir  # noqa: E402
from minisweagent.agents.default import DefaultAgent  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.models.test_models import make_output  # noqa: E402

import agent_core as ac  # noqa: E402
from mini_compress import CompressingDeterministicModel, CompressingTextbasedModel  # noqa: E402
from summarize import summarize  # noqa: E402

CONDITIONS = ("baseline", "intervention")
MINI_CONFIG = yaml.safe_load((package_dir / "config" / "mini_textbased.yaml").read_text())


# ---------------------------------------------------------------- 설정

def load_configs() -> dict:
    cfgs = {c: json.loads((EXPERIMENT / f"configs/{c}.json").read_text()) for c in CONDITIONS}
    for c, cfg in cfgs.items():
        if cfg.get("condition") != c:
            raise SystemExit(f"configs/{c}.json: condition 필드가 {c} 가 아닙니다")
    a, b = (copy.deepcopy(cfgs[c]) for c in CONDITIONS)
    for k in ("condition", "compression"):
        a.pop(k, None); b.pop(k, None)
    if a != b:
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        raise SystemExit(f"두 조건은 compression 외에 달라서는 안 됩니다. 다른 키: {diff}")
    return cfgs


def git_info() -> tuple[str, bool]:
    import subprocess
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except Exception:
        return "unknown", True
    return commit, dirty


# ---------------------------------------------------------------- 모델 생성

def make_model(cfg: dict, mode: str, seed: int, task: dict, condition: str, templates: dict | None = None):
    templates = templates or MINI_CONFIG
    comp = cfg["compression"]
    common = {"compression_enabled": comp["enabled"],
              "keep_last_observations": comp.get("keep_last_observations", 5),
              "placeholder": comp.get("placeholder", "(출력 {chars}자 생략됨)"),
              "context_tokens": cfg["limits"]["context_tokens"],
              "observation_template": templates["model"]["observation_template"]}
    if mode == "mock":
        return CompressingDeterministicModel(outputs=mock_outputs(task, condition), cost_per_call=0.0, **common)
    m = cfg["model"]
    api_base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
    return CompressingTextbasedModel(
        model_name=f"{m['litellm_provider']}/{m['name']}",
        model_kwargs={"api_base": api_base, "think": m["think"], "seed": seed, "drop_params": True,
                      "timeout": cfg["limits"].get("model_timeout_seconds", 600), **m["options"]},
        cost_tracking="ignore_errors",
        format_error_template=templates["model"]["format_error_template"],
        **common)


def mock_outputs(task: dict, condition: str) -> list[dict]:
    """mock 전용 fixture. 도구 출력 7개를 만들어 압축이 작동하게 하고, intervention 만 정답을 쓴다.
    이 차이는 사람이 정한 fixture 이며 개입 효과의 증거가 아니다."""
    repo = task["repo"]
    target = repo.get("target_file") or repo["file"]
    src = (repo.get("files") or {repo.get("file"): repo.get("content")})[target]
    if condition == "intervention":
        ref = task["reference"]
        if "buggy_solution" in ref:
            src = src.replace(ref["buggy_solution"].strip("\n"), ref["canonical_solution"].strip("\n"), 1)
        else:
            head, _, _ = src.partition('\n    """')
            doc = src.split('\n    """', 1)[1].split('"""\n', 1)[0]
            src = head + '\n    """' + doc + '"""\n' + ref["canonical_solution"]
    write = f"cat > {target} <<'PYEOF'\n" + src + "PYEOF"
    cmds = ["ls -la", "cat ISSUE.md", f"cat {target}", f"grep -n def {target}", "python3 -c 'print(1)'",
            f"cat {target}", write, "python3 -c 'print(\"ok\")'",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"]
    return [make_output(f"THOUGHT: step.\n\n```mswea_bash_command\n{c}\n```", [{"command": c}], cost=0.0) for c in cmds]


# ---------------------------------------------------------------- 한 번의 시도

def run_trial(task: dict, condition: str, cfg: dict, repeat: int, mode: str, out_dir: Path, run_id: str,
              dataset_name: str | None = None) -> dict:
    limits = cfg["limits"]
    seed = cfg["seeds"][repeat - 1]
    traj_path = out_dir / "trajectories" / task["task_id"] / condition / f"repeat-{repeat}.json"
    traj_path.parent.mkdir(parents=True, exist_ok=True)

    is_swe = task.get("kind") == "swebench"
    if is_swe:
        if mode != "real":
            raise SystemExit("SWE-bench 과제는 mock 모드를 지원하지 않는다(Docker 이미지 필요).")
        import swebench_support as sws
        templates = sws.SWEBENCH_CONFIG
        workdir = None
        env = sws.make_env(task, limits["command_timeout_seconds"])
    else:
        templates = MINI_CONFIG
        workdir = Path(tempfile.mkdtemp(prefix=f"e01-{task['task_id']}-{condition}-"))
        ac.build_task_workdir(task, workdir)
        if cfg["sandbox"]["kind"] != "local":
            raise SystemExit("HumanEvalFix 계열 과제는 sandbox.kind=local 만 지원한다.")
        env = LocalEnvironment(cwd=str(workdir), timeout=limits["command_timeout_seconds"],
                               env=MINI_CONFIG["environment"]["env"])
    model = make_model(cfg, mode, seed, task, condition, templates)
    agent = DefaultAgent(model, env,
                         system_template=templates["agent"]["system_template"],
                         instance_template=templates["agent"]["instance_template"],
                         step_limit=limits["max_turns"], cost_limit=0,
                         wall_time_limit_seconds=limits["wall_clock_seconds"],
                         max_consecutive_format_errors=limits["max_consecutive_format_errors"],
                         output_path=traj_path)
    t0 = time.monotonic()
    infra_error = None
    try:
        agent.run(task=task["issue"] if is_swe else ac.task_text(task))
    except Exception as e:  # mini 가 처리하지 못한 예외 = 인프라 오류 (모델 서버 다운 등)
        infra_error = f"{type(e).__name__}: {str(e)[:300]}"
    elapsed_ms = (time.monotonic() - t0) * 1000

    last_extra = (agent.messages[-1].get("extra") or {}) if agent.messages else {}
    exit_status = last_extra.get("exit_status", "")
    patch_source = None
    if is_swe:
        if exit_status == "Submitted":
            patch, patch_source = last_extra.get("submission", ""), "submitted"
        else:
            # 설계: 제출 없이 한도로 끝나도 최종 상태를 채점한다. 추적 파일의 변경만 뜬다(새로 만든 재현 스크립트 제외).
            patch, patch_source = "", "workdir_diff"
            if infra_error is None:
                try:
                    out = env.execute({"command": "git -c core.fileMode=false diff"}, timeout=120)
                    patch = out.get("output", "") if out.get("returncode") == 0 else ""
                except Exception:
                    patch = ""
        env.cleanup()
        graded = (sws.grade(task, patch, dataset_name, f"{run_id}-{task['task_id']}-{condition}-{repeat}")
                  if infra_error is None else {"status": "error", "reason": infra_error})
        final_snapshot = {"submission.patch": patch, "patch_source": patch_source}
    else:
        graded = ac.grade(task, workdir) if infra_error is None else {"status": "error", "reason": infra_error}
        final_snapshot = {str(p.relative_to(workdir)): p.read_text(errors="replace") for p in sorted(workdir.rglob("*"))
                          if p.is_file() and "__pycache__" not in p.parts and p.stat().st_size < 200_000}
        shutil.rmtree(workdir, ignore_errors=True)
    if graded.get("status") == "error" and infra_error is None:
        infra_error = graded.get("reason")

    # 토큰: mini 가 assistant 메시지 extra.response.usage 에 남긴 값을 합산
    in_tok = out_tok = 0
    tokens_measured = mode == "real"
    assistant = [m for m in agent.messages if m.get("role") == "assistant"]
    for m in assistant:
        usage = ((m.get("extra") or {}).get("response") or {}).get("usage") or {}
        if usage.get("prompt_tokens") is None:
            tokens_measured = False
        else:
            in_tok += usage["prompt_tokens"]; out_tok += usage.get("completion_tokens") or 0
    # FormatError 로 끝난 응답은 user 메시지의 extra.response 에 남는다
    for m in agent.messages:
        ex = m.get("extra") or {}
        if ex.get("interrupt_type") == "FormatError" and isinstance(ex.get("response"), dict):
            usage = ex["response"].get("usage") or {}
            if usage.get("prompt_tokens") is not None:
                in_tok += usage["prompt_tokens"]; out_tok += usage.get("completion_tokens") or 0

    compression_per_call = [(m.get("extra") or {}).get("compression", {}) for m in agent.messages
                            if "compression" in (m.get("extra") or {})]
    last_comp = compression_per_call[-1] if compression_per_call else {}
    tool_outputs_total = sum(ac.is_tool_output(m) for m in agent.messages)
    tail = [m.get("content") or "" for m in assistant[-10:]]
    repetition = any(ac.rouge_l_f1(a, b) >= 0.8 for a, b in zip(tail, tail[1:]))

    if graded["status"] == "success":
        status = "success"
    elif infra_error:
        status = "error"
    elif exit_status == "TimeExceeded":
        status = "timeout"
    else:
        status = "failure"

    agent.save(traj_path, {"e01": {"run_id": run_id, "task_id": task["task_id"], "condition": condition,
                                   "repeat_id": repeat, "seed": seed, "mode": mode, "grade": graded,
                                   "final_repo": final_snapshot, "infra_error": infra_error,
                                   "compression_per_call": compression_per_call}})
    # 공개용 정리: 레포·임시·홈 경로와 로컬 사용자명을 가린다(토큰 수·상태는 그대로)
    traj_path.write_text(ac.sanitize_text(traj_path.read_text(), ac.local_identifiers(ROOT)))

    missing = {"cost_usd": "local inference on own hardware; no per-token price"}
    if not tokens_measured:
        missing["input_tokens"] = missing["output_tokens"] = (
            "mock run: no model call" if mode == "mock" else "model response lacked token usage")
    return {"run_id": run_id, "task_id": task["task_id"], "condition": condition, "repeat_id": repeat,
            "status": status, "score": 1 if status == "success" else 0, "latency_ms": elapsed_ms,
            "input_tokens": in_tok if tokens_measured else None,
            "output_tokens": out_tok if tokens_measured else None, "cost_usd": None,
            "missing_reasons": missing,
            "evidence": {"config": f"configs/{condition}.json",
                         "trajectory": str(traj_path.relative_to(out_dir)),
                         "termination": exit_status or ("infra_error" if infra_error else "unknown"),
                         "turns": agent.n_calls, "seed": seed,
                         "compression_enabled": cfg["compression"]["enabled"],
                         "compressed_messages_last_turn": last_comp.get("compressed_messages", 0),
                         "tool_outputs_total": tool_outputs_total,
                         "repetition_detected": repetition,
                         "grader": graded.get("reason"), "grader_returncode": graded.get("returncode"),
                         "patch_source": patch_source,
                         "agent_framework": (f"mini-swe-agent {MINI_VERSION} DefaultAgent + DockerEnvironment, "
                                             f"config/benchmarks/swebench_backticks.yaml templates; graded by swebench harness")
                         if is_swe else (f"mini-swe-agent {MINI_VERSION} DefaultAgent + LocalEnvironment, "
                                         f"config/mini_textbased.yaml templates")}}


# ---------------------------------------------------------------- 메인

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--mode", choices=("real", "mock"), required=True,
                    help="real 은 litellm 경유로 Ollama 를 호출한다. mock 은 고정 응답으로 경로만 검증한다")
    ap.add_argument("--stage", choices=("pilot", "main"), default="pilot")
    ap.add_argument("--tasks", default=str(EXPERIMENT / "data/tasks.json"))
    ap.add_argument("--limit-tasks", type=int, help="앞에서부터 N개 과제만 (연습용)")
    ap.add_argument("--repeats", type=int, help="설정의 repeats 를 덮어쓴다 (연습용). manifest 에 기록됨")
    ap.add_argument("--resume", action="store_true", help="기존 run-id 폴더에 이어서 돈다. 끝난 시도는 건너뜀")
    args = ap.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.run_id):
        ap.error("run-id 는 영숫자, _, - 만")

    cfgs = load_configs()
    tasks_doc = json.loads(Path(args.tasks).read_text())
    tasks = tasks_doc["tasks"][: args.limit_tasks] if args.limit_tasks else tasks_doc["tasks"]
    task_ids = [t["task_id"] for t in tasks]
    repeats = args.repeats or cfgs["baseline"]["repeats"]
    for cfg in cfgs.values():
        if len(cfg["seeds"]) < repeats:
            ap.error("seeds 가 repeats 보다 적습니다")

    out = EXPERIMENT / "results" / args.stage / args.run_id
    if out.exists() and not args.resume:
        ap.error(f"{out} 이 이미 있습니다. 새 run-id 를 쓰거나 --resume")
    commit, dirty = git_info()  # 결과 폴더를 만들기 전에 읽어야 미추적 결과가 dirty 로 잡히지 않는다
    out.mkdir(parents=True, exist_ok=True)
    m = cfgs["baseline"]["model"]
    manifest = {
        "experiment_id": EXPERIMENT.name, "run_id": args.run_id, "stage": args.stage,
        "execution_mode": args.mode, "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": commit, "code_dirty": dirty,
        "model": m["name"] if args.mode == "real" else "mock-deterministic-outputs",
        "model_runtime": {"provider": "ollama via litellm", "litellm_model": f"{m['litellm_provider']}/{m['name']}",
                          "base_url_env": "OLLAMA_HOST", "think": m["think"],
                          "preserve_thinking": "n/a: previous assistant thinking is never forwarded (text mode, content only)"},
        "agent_framework": {"name": "mini-swe-agent", "version": MINI_VERSION,
                            "agent": "DefaultAgent",
                            "environment": "DockerEnvironment (linux/amd64)" if any(t.get("kind") == "swebench" for t in tasks)
                            else "LocalEnvironment",
                            "templates": ("minisweagent/config/benchmarks/swebench_backticks.yaml"
                                          if any(t.get("kind") == "swebench" for t in tasks)
                                          else "minisweagent/config/mini_textbased.yaml") + " (system, instance, observation, format_error)",
                            "hook": "src/mini_compress.py: Model.query() 직전 compress_old_observations"},
        "configs": cfgs, "task_ids": task_ids,
        "data_source": tasks_doc.get("source"), "data_selection": tasks_doc.get("selection"),
        "data_sha256": hashlib.sha256(Path(args.tasks).read_bytes()).hexdigest(),
        "repeats_per_condition": {c: repeats for c in CONDITIONS},
        "execution_order": "repeat -> task -> (baseline, intervention) interleaved; infra errors are logged as status=error, "
                           "re-runs use --resume after deleting the row and are listed in CARD",
        "seed_policy": f"seed per repeat from configs.seeds[:{repeats}]; passed to Ollama seed option, temperature 0",
        "cost_basis": "local inference; cost_usd null; input/output tokens from litellm usage (Ollama prompt_eval_count/eval_count)",
        "latency_basis": "wall clock per trial including model, command execution and grading",
        "environment": {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
                        "dependencies": f"mini-swe-agent=={MINI_VERSION} (litellm, pyyaml); grader uses standard library"},
        "warning": "mock mode uses human-written fixtures and is not evidence of intervention efficacy" if args.mode == "mock" else None,
    }
    prev_path = out / "manifest.json"
    if args.resume and prev_path.exists():
        # 이어 돌릴 때 이전 실행의 시작 시각·commit·반복 수를 잃지 않도록 쌓아 둔다
        prev = json.loads(prev_path.read_text())
        manifest["previous_runs"] = prev.pop("previous_runs", []) + [
            {k: prev.get(k) for k in ("started_at_utc", "code_commit", "code_dirty", "repeats_per_condition", "data_sha256")}]
    prev_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    trials_path = out / "trials.jsonl"
    done = set()
    if trials_path.exists():
        for line in trials_path.read_text().splitlines():
            if line.strip():
                r = json.loads(line); done.add((r["condition"], r["task_id"], r["repeat_id"]))
    with trials_path.open("a") as stream:
        for repeat in range(1, repeats + 1):
            for task in tasks:
                for cond in CONDITIONS:
                    if (cond, task["task_id"], repeat) in done:
                        continue
                    t = time.monotonic()
                    row = run_trial(task, cond, cfgs[cond], repeat, args.mode, out, args.run_id,
                                    dataset_name=(tasks_doc.get("source") or {}).get("dataset"))
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n"); stream.flush()
                    e = row["evidence"]
                    print(f"[{repeat}/{repeats}] {task['task_id']:>12} {cond:>12} {row['status']:>8} "
                          f"turns={e['turns']:>2} tools={e['tool_outputs_total']:>2} comp={e['compressed_messages_last_turn']:>2} "
                          f"term={e['termination']:<20} {(time.monotonic()-t):6.1f}s", flush=True)
    (out / "summary.json").write_text(json.dumps(summarize(out), ensure_ascii=False, indent=2) + "\n")
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
