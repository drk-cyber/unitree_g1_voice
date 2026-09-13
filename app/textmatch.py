"""唤醒词 / 停止词 / 确认词 的纯文本匹配。

纯函数、不碰音频，方便单测覆盖第 3 周验收标准里的各种说法。
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence, Tuple

# 中英文常见标点与空白（识别结果常带“小宇，请挥手。”这类标点）
_PUNCT_RE = re.compile(r"[\s，。！？!?.,、;；:：'\"“”‘’…·~～\-—]+")


def strip_punct(text: str) -> str:
    return _PUNCT_RE.sub("", text or "")


def extract_wake(text: str, wake_words: Sequence[str]) -> Tuple[Optional[str], str]:
    """文本以唤醒词开头 → (唤醒词, 去掉唤醒词及其后标点的剩余文本)。

    否则 → (None, 原文本)。唤醒词必须在最前面，"你好小宇" 不算唤醒。
    """
    t = (text or "").strip()
    for w in wake_words:
        if t.startswith(w):
            rest = t[len(w):].lstrip("，。！？!?.,、;；:：'\"“”…·\t ")
            return w, rest
    return None, t


def contains_stop(
    text: str,
    stop_words: Iterable[str],
    guard_words: Iterable[str] = (),
) -> bool:
    """文本是否命中“停止”指令。

    先查否定保护（“不要停下来”不是停止指令），再查停止词。
    宁可误停不可漏停：这里是 stop 直通的唯一判定点。
    """
    t = strip_punct(text)
    for g in guard_words:
        if g in t:
            return False
    return any(s in t for s in stop_words)


def is_affirmative(
    text: Optional[str],
    yes_words: Sequence[str],
    no_words: Sequence[str],
) -> bool:
    """确认答复判定。先查否定（“不可以”含“可以”，必须先判否定）。"""
    if not text:
        return False
    t = strip_punct(text)
    if not t:
        return False
    for n in no_words:
        if n in t:
            return False
    return any(y in t for y in yes_words)
