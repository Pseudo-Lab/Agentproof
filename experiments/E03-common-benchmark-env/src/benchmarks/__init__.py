"""벤치마크 등록. 새 벤치마크 = Benchmark 하위 클래스 하나 + 아래 사전에 한 줄.
원본 데이터 로더·프롬프트 이식은 다음 구현 단계 (README §6)."""

from .locomo import LoCoMo
from .longmemeval import LongMemEval

BENCHMARKS = {"locomo": LoCoMo, "longmemeval": LongMemEval}
