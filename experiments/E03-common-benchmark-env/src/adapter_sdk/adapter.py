"""알고리즘이 구현할 인터페이스.

원칙: 어댑터는 **메모리 연산(적재·검색)만** 한다. 답변 생성과 채점은 공통 평가 환경이 모든 알고리즘에
같은 프롬프트·모델로 수행한다. 그래야 결과 차이가 메모리 알고리즘 차이로만 남는다.
알고리즘 고유 답변기를 쓰고 싶으면 answer() 를 구현하고 공통 평가 환경을 --answer-mode native 로 돌린다
(이 결과는 통일 비교표와 따로 표시한다).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import Retrieval, Session


class MemoryAdapter(ABC):
    """scope 하나 = 서로 기억을 공유하지 않는 독립 메모리 하나.
    LoCoMo 는 대화 하나, LongMemEval 은 질문 하나가 scope 하나다."""

    name: str = "base"

    def setup(self, config: dict[str, Any]) -> dict[str, Any]:
        """프로세스 시작 시 1회. config 는 algorithm.toml 의 [config] 와 공통 평가 환경 설정(모델 등)을 합친 것.
        반환값(버전·모델·주요 하이퍼파라미터)은 결과 manifest 에 그대로 기록된다."""
        return {"name": self.name}

    @abstractmethod
    def reset(self, scope: str, speakers: list[str]) -> None:
        """새 scope 를 빈 메모리로 연다. speakers: LoCoMo ["Caroline", "Melanie"], LongMemEval ["user", "assistant"]."""

    @abstractmethod
    def ingest(self, scope: str, session: Session) -> None:
        """세션 하나를 적재한다. 몇 턴씩 묶을지, 화자별로 나눌지는 알고리즘이 정한다
        (예: Mem0 논문 방식은 2턴씩·화자별 역할 반전). 세션은 시간 순서대로 들어온다."""

    @abstractmethod
    def retrieve(self, scope: str, question: str, reference_date: str | None, top_k: int) -> Retrieval:
        """질문에 쓸 메모리를 찾는다. reference_date 는 질문 시점(LongMemEval question_date, LoCoMo 는 None)."""

    def answer(self, scope: str, question: str, reference_date: str | None,
               retrieval: Retrieval) -> str:
        """선택: 알고리즘 고유 답변기 (--answer-mode native 일 때만 호출)."""
        raise NotImplementedError

    def usage(self) -> dict[str, int]:
        """누적 사용량. 비용 집계에 쓴다. 키: llm_calls, tok_in, tok_out, embed_calls, tok_embed."""
        return {}

    def save(self, scope: str, path: str) -> None:
        """선택: scope 메모리를 디스크에 저장 (적재 결과 재사용·재개용)."""
        raise NotImplementedError

    def load(self, scope: str, path: str) -> None:
        """선택: save() 로 저장한 scope 메모리를 복원."""
        raise NotImplementedError

    def close(self, scope: str) -> None:
        """scope 를 닫고 메모리를 해제한다."""
