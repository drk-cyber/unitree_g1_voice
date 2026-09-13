"""意图解析（README 附录 B + 附录 D 备选方案）。

- OllamaIntentParser：Qwen 只输出固定 JSON，format="json" 约束 + pydantic 二次校验；
  任何失败（连不上 / 乱文本 / 非法 JSON / 未知 intent）都返回 None，由调用方降级。
- RuleBasedParser：关键词映射，不需要大模型；Jetson 内存紧张或 Ollama 未装时的后备。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.config import LLMConfig
from app.schemas import Intent, IntentResult

log = logging.getLogger("g1.llm")

SYSTEM_PROMPT = """你是人形机器人 G1 的指令解析器。
只能从 stand、sit、wave、stop、none 中选择一个 intent。
不能输出关节角度、速度或控制代码。
无法确定时返回 none。
只输出 JSON。

intent 含义：
- stand：让机器人站起来（例如“站起来”“起立”）
- sit：让机器人坐下（例如“坐下”“坐好”）
- wave：让机器人挥手打招呼（例如“挥手”“打个招呼”）
- stop：让机器人立即停止（例如“停止”“别动”）
- none：闲聊、提问、或机器人不会执行的动作（例如“跳舞”“跑步”“翻跟头”）

reply：一句简短的中文口语回复。执行类意图直接确认（如“好的，我来挥手。”）；
none 时能聊就简短回应（如“你好！”），做不到的指令就说明暂时不会（如“我暂时不会跳舞。”）。
confidence：你对 intent 判断的把握，0 到 1 之间的小数。

只输出如下格式的 JSON，不要输出任何其他内容：
{"intent": "wave", "reply": "好的，我来挥手。", "confidence": 0.92}"""

# 模型有时仍会包一层 ```json ... ```，直接抓最外层花括号
_JSON_RE = re.compile(r"\{.*\}", re.S)


def extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    m = _JSON_RE.search(raw)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


class RuleBasedParser:
    """关键词映射（附录 D 备选方案）。"""

    # 顺序有意义：stop 最先（安全优先），动作在后
    ACTION_KEYWORDS = [
        ("stop", ["停止", "停下", "停下来", "别动", "站住"]),
        ("stand", ["站起来", "起立", "站起", "站立"]),
        ("sit", ["坐下", "坐好", "坐下来"]),
        ("wave", ["挥手", "挥挥手", "打招呼", "打个招呼"]),
    ]
    NEGATION = ["不要", "别", "不准", "不能"]
    REPLIES = {
        "stand": "好的，我来站起来。",
        "sit": "好的，我来坐下。",
        "wave": "好的，我来挥手。",
        "stop": "好的，立即停止。",
        "none": "我暂时不会执行这个指令。",
    }

    def parse(self, text: str) -> IntentResult:
        t = text or ""
        # 1) stop 关键词优先
        for intent, words in self.ACTION_KEYWORDS:
            if intent == "stop" and any(w in t for w in words):
                return IntentResult(
                    intent=Intent.STOP, reply=self.REPLIES["stop"], confidence=0.9)
        # 2) 否定语 → 不是指令（“不要挥手”）
        if any(n in t for n in self.NEGATION):
            return IntentResult(
                intent=Intent.NONE, reply=self.REPLIES["none"], confidence=0.6)
        # 3) 普通动作
        for intent, words in self.ACTION_KEYWORDS:
            if intent != "stop" and any(w in t for w in words):
                return IntentResult(
                    intent=Intent(intent), reply=self.REPLIES[intent], confidence=0.85)
        return IntentResult(
            intent=Intent.NONE, reply=self.REPLIES["none"], confidence=0.4)


class OllamaIntentParser:
    def __init__(self, cfg: LLMConfig, client=None):
        self.cfg = cfg
        if client is None:
            import ollama

            client = ollama.Client(host=cfg.ollama.host, timeout=cfg.ollama.timeout)
        self._client = client

    def parse(self, text: str) -> Optional[IntentResult]:
        """返回 IntentResult；模型不可用 / 输出无法解析时返回 None（调用方可退回规则解析）。"""
        try:
            resp = self._client.chat(
                model=self.cfg.ollama.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"用户说：{text}"},
                ],
                format="json",
                options={
                    "temperature": self.cfg.ollama.temperature,
                    "num_predict": 120,
                },
            )
            raw = resp["message"]["content"]
        except Exception as e:
            log.warning("Ollama 调用失败：%s", e)
            return None
        data = extract_json(raw)
        if data is None:
            log.warning("模型输出不是 JSON：%r", raw)
            return None
        try:
            return IntentResult.model_validate(data)
        except Exception as e:
            log.warning("意图 JSON 校验失败（按 none 处理）：%s / %r", e, data)
            return None
