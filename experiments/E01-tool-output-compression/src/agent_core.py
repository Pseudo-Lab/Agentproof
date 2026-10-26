"""E01 핵심 로직: 도구 출력 압축, 과제 작업 디렉터리, 숨겨진 테스트 채점, 반복 탐지.

에이전트 루프·명령 실행·응답 파싱은 mini-swe-agent(2.4.6) 것을 그대로 쓴다. 이 모듈은 import 만으로는
모델이나 외부 서비스를 호출하지 않는다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------- 도구 출력 판별과 압축

def is_tool_output(message: dict) -> bool:
    """역할 이름이 아니라 extra 필드로 도구 출력을 판별한다. 과제 문장도 user 역할이기 때문이다.

    mini-swe-agent 텍스트 모드는 관찰 메시지의 extra 에 raw_output 과 returncode 를 넣는다.
    """
    extra = message.get("extra") or {}
    return "raw_output" in extra or bool(extra.get("tool_output"))


def compress_old_observations(messages: list[dict], keep_last: int,
                              placeholder: str = "(출력 {chars}자 생략됨)") -> tuple[list[dict], dict]:
    """가장 최근 keep_last 개의 도구 출력만 전문으로 두고, 더 오래된 도구 출력은 한 줄로 바꾼다.

    원본 리스트와 원본 메시지 dict 는 바꾸지 않는다. 새 리스트를 돌려준다.
    시스템 프롬프트, 과제 문장, 모델 응답은 어떤 경우에도 건드리지 않는다.
    """
    if keep_last < 0:
        raise ValueError("keep_last must be >= 0")
    tool_indices = [i for i, m in enumerate(messages) if is_tool_output(m)]
    to_compress = set(tool_indices[:-keep_last] if keep_last else tool_indices)
    out, compressed_count, removed_chars = [], 0, 0
    for i, m in enumerate(messages):
        if i in to_compress:
            n = len(m["content"])
            new = dict(m)
            new["content"] = placeholder.format(chars=n)
            new["extra"] = dict(m.get("extra") or {}, compressed=True, original_chars=n)
            out.append(new)
            compressed_count += 1
            removed_chars += n
        else:
            out.append(m)
    stats = {"compressed_messages": compressed_count, "removed_chars": removed_chars,
             "tool_outputs_total": len(tool_indices)}
    return out, stats


def estimate_tokens(messages: list[dict]) -> int:
    """토크나이저 없이 쓰는 보수적 추정. 문자 3개를 토큰 1개로 본다."""
    return sum(len(m.get("content") or "") for m in messages if isinstance(m.get("content"), str)) // 3 + 64


# ---------------------------------------------------------------- 과제와 채점

def build_task_workdir(task: dict, workdir: Path) -> None:
    """에이전트에게 보여 줄 저장소를 만든다. 숨겨진 테스트와 정답은 넣지 않는다."""
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / task["repo"]["file"]).write_text(task["repo"]["content"])
    (workdir / "ISSUE.md").write_text(task["issue"] + "\n")


def task_text(task: dict) -> str:
    """mini 의 instance_template 에 {{task}} 로 들어가는 문장."""
    return f"{task['issue']}\nThe repository is in the current working directory. See ISSUE.md."


def grade(task: dict, workdir: Path, timeout: float = 30.0) -> dict:
    """작업 디렉터리의 최종 상태를 숨겨진 테스트로 채점한다.

    테스트는 에이전트 작업 디렉터리 밖(임시 디렉터리)에서, 하네스가 보관한 원본 테스트 코드로 돌린다.
    에이전트가 저장소 안 파일을 어떻게 고쳤든 테스트 코드 자체는 영향받지 않는다.
    """
    target = workdir / task["repo"]["file"]
    if not target.exists():
        return {"status": "failure", "reason": "solution file missing", "returncode": None, "output": ""}
    hidden = task["hidden_test"]
    program = (hidden.get("imports", "") + "\n" + hidden.get("setup", "") + "\n"
               + target.read_text() + "\n" + hidden["test"] + f"\ncheck({hidden['entry_point']})\n")
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "run_hidden_test.py"
        script.write_text(program)
        try:
            p = subprocess.run([sys.executable, "-I", str(script)], cwd=tmp, capture_output=True,
                               text=True, timeout=timeout, errors="replace")
        except subprocess.TimeoutExpired:
            return {"status": "failure", "reason": "hidden test timed out", "returncode": None, "output": ""}
    ok = p.returncode == 0
    return {"status": "success" if ok else "failure",
            "reason": "all hidden tests passed" if ok else "hidden test failed or crashed",
            "returncode": p.returncode, "output": (p.stdout + p.stderr)[-2000:]}


# ---------------------------------------------------------------- 반복 탐지

def rouge_l_f1(a: str, b: str) -> float:
    """단어 단위 LCS 기반 Rouge-L F1. 마지막 턴들의 반복 탐지에 쓴다."""
    x, y = a.split(), b.split()
    if not x or not y:
        return 0.0
    prev = [0] * (len(y) + 1)
    for xi in x:
        cur = [0]
        for j, yj in enumerate(y, 1):
            cur.append(prev[j - 1] + 1 if xi == yj else max(prev[j], cur[j - 1]))
        prev = cur
    lcs = prev[-1]
    if lcs == 0:
        return 0.0
    p, r = lcs / len(x), lcs / len(y)
    return 2 * p * r / (p + r)


# ---------------------------------------------------------------- 공개용 로그 정리

def local_identifiers(repo_root: Path) -> list[tuple[str, str]]:
    """공개 로그에서 가릴 로컬 식별자와 대체 문자열. 긴 것부터 바꾼다.

    가리는 것: 레포 절대 경로, 임시 디렉터리 경로, 홈 경로, 로컬 사용자명(ls -l 의 소유자 칸 등).
    """
    import getpass
    import os
    pairs = [(str(Path(repo_root).resolve()), "<repo>")]
    for tmp in {tempfile.gettempdir(), os.path.realpath(tempfile.gettempdir())}:
        pairs.append((tmp.rstrip("/"), "<tmp>"))
    pairs.append((str(Path.home()), "~"))
    user = getpass.getuser()
    if len(user) >= 3:
        pairs.append((user, "user"))
    return sorted(set(pairs), key=lambda p: -len(p[0]))


def sanitize_text(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text
