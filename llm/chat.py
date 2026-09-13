"""第2周对话原型用的闲聊（assistant 模式不用这个，走意图解析）。"""
from __future__ import annotations

import logging
from typing import Optional

from app.config import LLMConfig

log = logging.getLogger("g1.llm")

SYSTEM_PROMPT = (
    "你是人形机器人 G1 的语音助手“小宇”。"
    "用一两句简短的中文口语回答用户，不要列表、不要 Markdown 格式符号。"
)


class OllamaChat:
    def __init__(self, cfg: LLMConfig, client=None):
        self.cfg = cfg
        if client is None:
            import ollama

            client = ollama.Client(host=cfg.ollama.host, timeout=cfg.ollama.timeout)
        self._client = client

    def reply(self, text: str) -> Optional[str]:
        """返回回答文本；Ollama 不可用时返回 None（不抛异常）。"""
        try:
            resp = self._client.chat(
                model=self.cfg.ollama.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                options={"temperature": 0.7, "num_predict": 160},
            )
            return (resp["message"]["content"] or "").strip()
        except Exception as e:
            log.warning("Ollama 闲聊失败：%s", e)
            return None
