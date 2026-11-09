"""3순위 묶음(SWE-bench Lite)용 환경 생성과 채점.

- 에이전트 환경: mini 의 DockerEnvironment 로 과제 이미지(`swebench/sweb.eval.x86_64.*`)를 띄운다.
  Apple Silicon 에서는 `--platform linux/amd64` 로 에뮬레이션한다.
- 프롬프트·관찰 템플릿: mini 의 `config/benchmarks/swebench_backticks.yaml` (텍스트 모드) 그대로.
- 채점: SWE-bench 공식 하네스(`swebench.harness.run_evaluation`)를 새 컨테이너에서 돌린다.
  에이전트가 제출한 패치만 적용하고, 숨겨진 FAIL_TO_PASS / PASS_TO_PASS 테스트로 판정한다.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from minisweagent import package_dir
from minisweagent.environments.docker import DockerEnvironment

SWEBENCH_CONFIG = yaml.safe_load((package_dir / "config" / "benchmarks" / "swebench_backticks.yaml").read_text())
PLATFORM_ARGS = ["--platform", "linux/amd64"]


def make_env(task: dict, command_timeout: int) -> DockerEnvironment:
    env_cfg = SWEBENCH_CONFIG["environment"]
    return DockerEnvironment(image=task["repo"]["image"], cwd=task["repo"].get("cwd", "/testbed"),
                             timeout=command_timeout, interpreter=env_cfg.get("interpreter", ["bash", "-c"]),
                             env=env_cfg.get("env", {}), run_args=["--rm", *PLATFORM_ARGS], pull_timeout=1200)


def ensure_image(image: str) -> None:
    """하네스는 플랫폼을 지정하지 않고 이미지를 받으려다 arm64 에서 실패하므로 amd64 로 미리 받아 둔다."""
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        subprocess.run(["docker", "pull", "-q", *PLATFORM_ARGS, image], capture_output=True, timeout=1800, check=True)


def grade(task: dict, patch: str, dataset_name: str, run_id: str, timeout: int = 1800) -> dict:
    """공식 하네스로 패치 하나를 채점한다. 하네스가 보고서를 못 만들면 status=error."""
    iid = task["task_id"]
    ensure_image(task["repo"]["image"])
    if not (patch or "").strip():
        return {"status": "failure", "reason": "empty patch", "returncode": None, "report": None}
    with tempfile.TemporaryDirectory() as tmp:
        preds = Path(tmp) / "preds.json"
        preds.write_text(json.dumps([{"instance_id": iid, "model_name_or_path": "e01", "model_patch": patch}]))
        try:
            p = subprocess.run([sys.executable, "-m", "swebench.harness.run_evaluation",
                                "--dataset_name", dataset_name, "--split", "test", "--instance_ids", iid,
                                "--predictions_path", str(preds), "--max_workers", "1", "--run_id", run_id,
                                "--timeout", str(timeout), "--report_dir", tmp],
                               cwd=tmp, capture_output=True, text=True, timeout=timeout + 600, errors="replace")
        except subprocess.TimeoutExpired:
            return {"status": "error", "reason": "harness timed out", "returncode": None, "report": None}
        reports = list(Path(tmp).glob(f"e01.{run_id}.json"))
        inst = list(Path(tmp).glob(f"logs/run_evaluation/{run_id}/e01/{iid}/report.json"))
        if not reports:
            return {"status": "error", "reason": "harness produced no report", "returncode": p.returncode,
                    "output": (p.stdout + p.stderr)[-2000:], "report": None}
        summary = json.loads(reports[0].read_text())
        detail = json.loads(inst[0].read_text()).get(iid) if inst else None
    if iid in summary.get("resolved_ids", []):
        return {"status": "success", "reason": "resolved (FAIL_TO_PASS and PASS_TO_PASS pass)", "returncode": 0,
                "report": detail}
    applied = (detail or {}).get("patch_successfully_applied")
    if applied is None and "Patch Apply Failed" in (p.stdout + p.stderr):
        # 하네스는 적용 실패를 error_ids 로 분류하고 개별 보고서를 남기지 않는다. 사전 규칙상 failure
        applied = False
    if iid in summary.get("error_ids", []) and applied is not False:
        return {"status": "error", "reason": "harness error during evaluation", "returncode": p.returncode,
                "output": (p.stdout + p.stderr)[-2000:], "report": detail}
    reason = "patch did not apply" if applied is False else "unresolved (hidden tests failed)"
    return {"status": "failure", "reason": reason, "returncode": 1, "report": detail}
