"""배선 확인용 예시 어댑터. 새 알고리즘을 만들 때 이 파일을 복사해서 시작한다.

적재: 발화를 그대로 저장한다. 검색: 질문과 겹치는 단어 수로 점수를 매겨 top_k 를 돌려준다.
LLM·임베딩을 쓰지 않으므로 점수는 메모리 성능과 무관하다.
"""

from __future__ import annotations

import re

from adapter_sdk import Item, MemoryAdapter, Retrieval, Session


def words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


class ExampleAdapter(MemoryAdapter):
    name = "example"

    def setup(self, config):
        self.scopes: dict[str, list[Item]] = {}
        return {"name": self.name, "retrieval": "word-overlap"}

    def reset(self, scope, speakers):
        self.scopes[scope] = []

    def ingest(self, scope, session: Session):
        for turn in session.turns:
            self.scopes[scope].append(Item(text=f"{turn.speaker}: {turn.text}", timestamp=session.date,
                                           owner=turn.speaker, source_turn_ids=[turn.turn_id]))

    def retrieve(self, scope, question, reference_date, top_k) -> Retrieval:
        q = words(question)
        ranked = sorted(self.scopes[scope], key=lambda item: len(q & words(item.text)), reverse=True)
        return Retrieval(items=[Item(**{**vars(i), "score": float(len(q & words(i.text)))}) for i in ranked[:top_k]])

    def usage(self):
        return {"llm_calls": 0, "tok_in": 0, "tok_out": 0, "embed_calls": 0, "tok_embed": 0}

    def close(self, scope):
        self.scopes.pop(scope, None)
