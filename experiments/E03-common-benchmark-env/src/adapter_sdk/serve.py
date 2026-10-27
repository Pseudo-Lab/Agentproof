"""어댑터 작업 프로세스. 공통 평가 환경이 알고리즘 venv 의 python 으로 이 모듈을 띄운다.

    <algo-venv>/bin/python -m adapter_sdk.serve algorithms.mem0.adapter:Mem0Adapter

규약 (JSON Lines, 한 줄에 메시지 하나):
    요청  stdin  {"id": 1, "method": "ingest", "params": {...}}
    응답  stdout {"id": 1, "ok": true, "result": ..., "seconds": 0.12}
               {"id": 1, "ok": false, "error": "ValueError: ...", "traceback": "..."}
stdout 은 응답 전용이다. 알고리즘 라이브러리가 print 하는 내용은 stderr 로 돌린다.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
import traceback

from .adapter import MemoryAdapter
from .types import Retrieval, Session

METHODS = ("setup", "reset", "ingest", "retrieve", "answer", "usage", "save", "load", "close")


def load_adapter(spec: str) -> MemoryAdapter:
    module_name, _, class_name = spec.partition(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    return cls()


def dispatch(adapter: MemoryAdapter, method: str, params: dict):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    if method == "ingest":
        params = {**params, "session": Session.from_dict(params["session"])}
    if method == "answer":
        params = {**params, "retrieval": Retrieval.from_dict(params["retrieval"])}
    result = getattr(adapter, method)(**params)
    return result.to_dict() if isinstance(result, Retrieval) else result


def main() -> int:
    adapter = load_adapter(sys.argv[1])
    out = sys.stdout
    sys.stdout = sys.stderr  # 라이브러리 print 가 규약 채널을 더럽히지 않게 한다
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        started = time.perf_counter()
        try:
            result = dispatch(adapter, msg["method"], msg.get("params") or {})
            reply = {"id": msg["id"], "ok": True, "result": result}
        except Exception as exc:  # 공통 평가 환경이 실패를 기록하고 재개할 수 있게 프로세스는 살려 둔다
            reply = {"id": msg["id"], "ok": False, "error": f"{type(exc).__name__}: {exc}",
                     "traceback": traceback.format_exc()}
        reply["seconds"] = time.perf_counter() - started
        out.write(json.dumps(reply, ensure_ascii=False) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
