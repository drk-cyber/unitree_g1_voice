"""意图 JSON 模式（README 附录 B）与白名单校验。

大模型只允许输出这个结构；intent 只能是五个枚举值之一，
任何越界（乱文本、非法 JSON、未知动作）在解析层都会失败，
由调用方安全降级为 none，绝不放行动作。
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, field_validator


class Intent(str, Enum):
    STAND = "stand"
    SIT = "sit"
    WAVE = "wave"
    STOP = "stop"
    NONE = "none"


class IntentResult(BaseModel):
    intent: Intent = Intent.NONE
    reply: str = ""
    confidence: float = 0.0

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        """模型偶尔输出 1.2 之类的越界值，夹紧而不是整条拒绝。"""
        return max(0.0, min(1.0, float(v)))

    @field_validator("reply")
    @classmethod
    def _trim_reply(cls, v: str) -> str:
        v = (v or "").strip()
        return v[:80]  # 播报用，太长就截断

    @property
    def is_action(self) -> bool:
        """stand / sit / wave 需要走确认与冷却；stop 与 none 不算普通动作。"""
        return self.intent in (Intent.STAND, Intent.SIT, Intent.WAVE)
