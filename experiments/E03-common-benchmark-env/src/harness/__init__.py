"""공통 평가 환경 — 전용 venv(src/.venv)에서 실행된다.

알고리즘 코드는 import 하지 않는다. 알고리즘은 각자의 venv 에서 adapter_sdk.serve 하위 프로세스로 돌고,
공통 평가 환경은 JSON Lines 로 적재·검색을 요청한다(worker.py). 답변 생성·채점·집계는 전부 여기서 한다.
"""
