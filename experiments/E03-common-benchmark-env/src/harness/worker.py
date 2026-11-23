"""알고리즘 venv 의 python 으로 adapter_sdk.serve 를 띄우고 JSON Lines 로 호출한다.

병렬 처리 단위는 작업 프로세스다. --workers N 이면 같은 알고리즘 프로세스 N 개를 띄우고
scope(대화/질문)를 나눠 맡긴다. 한 프로세스 안에서는 요청을 순서대로 처리한다.
"""

from __future__ import annotations

import itertools
import json
import os
import subprocess
from pathlib import Path

from .registry import ROOT, AlgorithmSpec


class AdapterError(RuntimeError):
    def __init__(self, method: str, reply: dict):
        super().__init__(f"{method}: {reply.get('error')}")
        self.traceback = reply.get("traceback", "")


class AdapterProcess:
    def __init__(self, spec: AlgorithmSpec, log_path: Path | None = None, env: dict | None = None):
        if not spec.python.exists():
            raise FileNotFoundError(f"{spec.name} 가상환경이 없다: {spec.venv}  →  scripts/setup_venv.sh {spec.name}")
        self._log = open(log_path, "a") if log_path else None   # 알고리즘 로그·print 는 여기로
        self.spec = spec
        self.proc = subprocess.Popen(
            [str(spec.python), "-m", "adapter_sdk.serve", spec.adapter],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log, text=True,
            env={**os.environ, "PYTHONPATH": str(ROOT), **(env or {})})
        self._ids = itertools.count(1)

    def call(self, method: str, **params):
        """(result, seconds) 를 돌려준다. seconds 는 어댑터 안에서 잰 순수 처리 시간."""
        msg_id = next(self._ids)
        self.proc.stdin.write(json.dumps({"id": msg_id, "method": method, "params": params},
                                         ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError(f"{self.spec.name} 작업 프로세스가 종료됐다 (exit {self.proc.poll()})")
        reply = json.loads(line)
        if reply["id"] != msg_id:
            raise RuntimeError("응답 id 불일치")
        if not reply["ok"]:
            raise AdapterError(method, reply)
        return reply["result"], reply["seconds"]

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=30)
        self.proc.stdout.close()
        if self._log:
            self._log.close()
