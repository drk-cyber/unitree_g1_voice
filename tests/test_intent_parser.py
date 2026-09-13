"""意图解析器：规则版 + Ollama 版（含乱输出容错，第3周验收）。"""
import pytest

from app.schemas import Intent, IntentResult
from llm.intent_parser import (
    OllamaIntentParser,
    RuleBasedParser,
    extract_json,
)
from app.config import LLMConfig


class FakeOllamaClient:
    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc

    def chat(self, **kwargs):
        if self.exc:
            raise self.exc
        return {"message": {"content": self.content}}


def make_parser(content=None, exc=None):
    return OllamaIntentParser(LLMConfig(), client=FakeOllamaClient(content, exc))


# ---------------- 规则解析 ----------------

class TestRuleBasedParser:
    @pytest.mark.parametrize("text,intent", [
        ("请站起来", "stand"),
        ("起立", "stand"),
        ("坐下", "sit"),
        ("挥挥手", "wave"),
        ("打个招呼", "wave"),
        ("停止", "stop"),
        ("别动", "stop"),
    ])
    def test_actions(self, text, intent):
        assert RuleBasedParser().parse(text).intent.value == intent

    @pytest.mark.parametrize("text", ["跳起来", "跳个舞", "今天天气怎么样", "你好"])
    def test_none(self, text):
        r = RuleBasedParser().parse(text)
        assert r.intent is Intent.NONE

    def test_negation_is_not_action(self):
        assert RuleBasedParser().parse("不要挥手").intent is Intent.NONE


# ---------------- Ollama 解析 ----------------

class TestOllamaIntentParser:
    def test_valid_json(self):
        p = make_parser(content='{"intent": "wave", "reply": "好的，我来挥手。", "confidence": 0.92}')
        r = p.parse("请挥手")
        assert r.intent is Intent.WAVE
        assert r.reply == "好的，我来挥手。"
        assert r.confidence == 0.92

    def test_json_in_markdown_fence(self):
        content = '```json\n{"intent": "stand", "confidence": 0.9}\n```'
        r = make_parser(content=content).parse("站起来")
        assert r.intent is Intent.STAND

    def test_garbage_text_returns_none(self):
        # 模型返回乱文本 → None（调用方降级，不放行动作）
        assert make_parser(content="我不会").parse("挥手") is None

    def test_invalid_json_returns_none(self):
        assert make_parser(content='{"intent": "wave",').parse("挥手") is None

    def test_unknown_intent_returns_none(self):
        # intent 越界（dance）→ 校验失败 → None
        assert make_parser(content='{"intent": "dance"}').parse("跳舞") is None

    def test_connection_error_returns_none(self):
        p = make_parser(exc=ConnectionError("ollama 没开"))
        assert p.parse("挥手") is None

    def test_confidence_clamped(self):
        r = make_parser(content='{"intent": "sit", "confidence": 1.5}').parse("坐下")
        assert r.confidence == 1.0


def test_extract_json():
    assert extract_json('xx {"a": 1} yy') == {"a": 1}
    assert extract_json("没有花括号") is None
    assert extract_json('{"a": [1,2]}') == {"a": [1, 2]}
