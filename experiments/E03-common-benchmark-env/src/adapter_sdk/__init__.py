"""알고리즘 어댑터 SDK — 알고리즘별 가상환경 안에서 import 된다.

표준 라이브러리만 쓴다. 어느 venv(파이썬 3.10 이상)에서도 의존성 없이 올라가야 하기 때문이다.
공통 평가 환경(harness/)과 공유하는 것은 이 패키지의 데이터 형식과 메시지 규약뿐이다.
"""

from .adapter import MemoryAdapter
from .types import Item, Retrieval, Session, Turn

__all__ = ["MemoryAdapter", "Item", "Retrieval", "Session", "Turn"]
