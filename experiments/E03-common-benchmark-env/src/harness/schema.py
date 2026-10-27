"""벤치마크를 공통 평가 환경의 형식으로 바꾼 결과. 벤치마크 로더(benchmarks/*.py)가 만든다."""

from __future__ import annotations

from dataclasses import dataclass, field

from adapter_sdk.types import Session


@dataclass
class Question:
    question_id: str             # LoCoMo "conv-26:12" (원래 qa 인덱스 보존) / LongMemEval question_id
    question: str
    answer: str
    category: str                # LoCoMo "1".."5"(정수 번호 문자열) / LongMemEval question_type(+"_abs")
    reference_date: str | None = None
    evidence: list[str] = field(default_factory=list)   # 근거 턴 id (회수율 계산용)


@dataclass
class Episode:
    """독립 메모리 scope 하나: 세션들을 시간 순서대로 적재한 뒤 questions 에 답한다."""
    episode_id: str
    speakers: list[str]
    sessions: list[Session]
    questions: list[Question]
