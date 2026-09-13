"""IDLE / LISTENING / PROCESSING 状态机（阶段1 第3周）。

IDLE       等待唤醒词（“停止”直通也在此层拦截）
LISTENING  已唤醒、等待指令；超过 listen_timeout 无语音 → 回 IDLE
PROCESSING 正在识别/解析/派发；完成后回 IDLE

非法转移一律返回 False（比如 LISTENING 里再次 wake），
状态机自己永远不会抛异常。
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable


class State(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"


class StateMachine:
    def __init__(self, listen_timeout: float = 2.5, clock: Callable[[], float] = time.monotonic):
        self.listen_timeout = listen_timeout
        self._clock = clock
        self._state = State.IDLE
        self._since = clock()

    @property
    def state(self) -> State:
        return self._state

    @property
    def since(self) -> float:
        return self._since

    def _to(self, s: State) -> None:
        self._state = s
        self._since = self._clock()

    def wake(self) -> bool:
        """IDLE → LISTENING（听到“小宇”，等指令）。"""
        if self._state is State.IDLE:
            self._to(State.LISTENING)
            return True
        return False

    def command(self) -> bool:
        """IDLE|LISTENING → PROCESSING（“小宇，挥手”一句话直达，或唤醒后听到指令）。"""
        if self._state in (State.IDLE, State.LISTENING):
            self._to(State.PROCESSING)
            return True
        return False

    def done(self) -> bool:
        """PROCESSING → IDLE（本轮处理完毕）。"""
        if self._state is State.PROCESSING:
            self._to(State.IDLE)
            return True
        return False

    def timeout(self) -> bool:
        """LISTENING → IDLE（等不到指令，回待命）。"""
        if self._state is State.LISTENING:
            self._to(State.IDLE)
            return True
        return False

    def reset(self) -> None:
        """任何状态 → IDLE（异常恢复用）。"""
        self._to(State.IDLE)

    def is_listen_expired(self) -> bool:
        return (
            self._state is State.LISTENING
            and (self._clock() - self._since) >= self.listen_timeout
        )
