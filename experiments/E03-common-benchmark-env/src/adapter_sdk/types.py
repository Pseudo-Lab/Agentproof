"""공통 평가 환경 ↔ 어댑터가 주고받는 데이터 형식. JSON 직렬화가 되는 평범한 dataclass 만 둔다."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Turn:
    """발화 하나. speaker 는 데이터셋 원문 이름(LoCoMo: "Caroline"), role 은 user/assistant."""
    speaker: str
    role: str
    text: str
    turn_id: str = ""            # LoCoMo dia_id("D1:3") / LongMemEval "<session_id>:<index>"
    has_answer: bool | None = None  # LongMemEval 근거 표시(검색 지표용). 어댑터는 쓰지 않는다.


@dataclass
class Session:
    """세션 하나. date 는 데이터셋 원문 문자열(형식이 벤치마크마다 다르다)과 ISO 날짜를 함께 준다."""
    session_id: str
    date: str
    date_iso: str | None
    turns: list[Turn]

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(d["session_id"], d["date"], d.get("date_iso"), [Turn(**t) for t in d["turns"]])


@dataclass
class Item:
    """검색된 메모리 하나. owner 는 화자별 저장소를 쓰는 알고리즘(Mem0 논문 방식)이 채운다."""
    text: str
    timestamp: str | None = None
    score: float | None = None
    owner: str | None = None
    source_turn_ids: list[str] = field(default_factory=list)  # 근거 회수율(recall@k) 계산용, 선택


@dataclass
class Retrieval:
    """retrieve() 결과. context 를 채우면 공통 평가 환경은 items 대신 이 문자열을 답변 프롬프트에 넣는다
    (그래프 경로처럼 목록으로 표현하기 어려운 문맥을 내는 알고리즘용)."""
    items: list[Item]
    context: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Retrieval":
        return cls([Item(**i) for i in d.get("items", [])], d.get("context"), d.get("extra") or {})
