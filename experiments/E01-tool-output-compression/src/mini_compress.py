"""mini-swe-agent 위에 도구 출력 압축을 끼워 넣는 모델 클래스.

개입 지점은 Model.query() 직전 하나다. DefaultAgent 와 Environment 는 mini 것을 그대로 쓴다.
baseline 은 compression_enabled=false 로 같은 클래스를 쓰므로, 두 조건의 코드 경로 차이는
_prepare() 안의 if 한 줄이다.
"""
from __future__ import annotations

from minisweagent.exceptions import FormatError, LimitsExceeded
from minisweagent.models.litellm_model import LitellmModel
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel, LitellmTextbasedModelConfig
from minisweagent.models.test_models import DeterministicModel, DeterministicModelConfig

from agent_core import compress_old_observations, estimate_tokens, is_tool_output


class CompressionConfigMixin:
    compression_enabled: bool = False
    keep_last_observations: int = 5
    placeholder: str = "(출력 {chars}자 생략됨)"
    context_tokens: int = 0
    """0 이면 문맥 초과 검사를 하지 않는다."""


class CompressingTextbasedModelConfig(CompressionConfigMixin, LitellmTextbasedModelConfig):
    pass


class CompressingDeterministicModelConfig(CompressionConfigMixin, DeterministicModelConfig):
    pass


def _overflow_exit(reason: str, **extra) -> dict:
    return {"role": "exit", "content": "ContextOverflow",
            "extra": {"exit_status": "ContextOverflow", "submission": "", "reason": reason, **extra}}


class _CompressingQuery:
    """query() 를 감싸서 (1) 압축 (2) 문맥 초과 검사 (3) 통계 기록을 한다."""

    def _prepare(self, messages: list[dict]) -> tuple[list[dict], dict]:
        if self.config.compression_enabled:
            return compress_old_observations(messages, self.config.keep_last_observations, self.config.placeholder)
        return messages, {"compressed_messages": 0, "removed_chars": 0,
                          "tool_outputs_total": sum(is_tool_output(m) for m in messages)}

    def query(self, messages: list[dict], **kwargs) -> dict:
        sent, stats = self._prepare(messages)
        stats["estimated_prompt_tokens"] = estimate_tokens(sent)
        if self.config.context_tokens and stats["estimated_prompt_tokens"] > self.config.context_tokens:
            raise LimitsExceeded(_overflow_exit("estimated prompt exceeds context window", compression=stats))
        try:
            message = super().query(sent, **kwargs)
        except FormatError as e:
            e.messages[0].setdefault("extra", {})["compression"] = stats
            raise
        message.setdefault("extra", {})["compression"] = stats
        usage = (message["extra"].get("response") or {}).get("usage") or {}
        prompt_tokens = usage.get("prompt_tokens")
        if self.config.context_tokens and prompt_tokens is not None and prompt_tokens >= self.config.context_tokens - 64:
            # Ollama 는 num_ctx 를 넘는 입력을 조용히 잘라낸다. 응답을 로그에 남긴 뒤 종료한다.
            raise LimitsExceeded(message, _overflow_exit("server reported prompt_tokens at context window",
                                                         prompt_tokens=prompt_tokens))
        return message


class CompressingTextbasedModel(_CompressingQuery, LitellmTextbasedModel):
    def __init__(self, **kwargs):
        # LitellmTextbasedModel.__init__ 은 config_class 를 고정하므로 한 단계 위 생성자를 직접 부른다.
        LitellmModel.__init__(self, config_class=CompressingTextbasedModelConfig, **kwargs)


class CompressingDeterministicModel(_CompressingQuery, DeterministicModel):
    """mock 전용. 고정 응답을 돌려주되 압축 경로는 실제와 같이 탄다."""

    def __init__(self, **kwargs):
        self.config = CompressingDeterministicModelConfig(**kwargs)
        self.current_index = -1
