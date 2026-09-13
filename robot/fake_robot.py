"""FakeRobot：没有真机时的模拟机器人（阶段1 全部逻辑先在它身上跑通）。

只认识 stand / sit / wave / stop —— 它自己是白名单的第二道防线
（第一道在 SafetyLayer）。
"""
from __future__ import annotations

import logging
import time
from typing import List, Tuple

log = logging.getLogger("g1.robot")

SUPPORTED = ("stand", "sit", "wave")


class FakeRobot:
    def __init__(self, action_seconds: float = 0.0):
        self.action_seconds = action_seconds  # 模拟动作耗时
        self.state = "idle"                   # idle | executing:<action> | stopped
        self.history: List[Tuple[float, str, str]] = []  # (时间, 动作, 结果)

    def perform(self, action: str) -> Tuple[bool, str]:
        """执行一个动作。返回 (ok, message)，未知动作一律拒绝。"""
        if action == "stop":
            return self.stop()
        if action not in SUPPORTED:
            log.warning("FakeRobot 拒绝未知动作：%s", action)
            return False, f"未知动作: {action}"
        self.state = f"executing:{action}"
        log.info("FakeRobot 执行 %s ……", action)
        if self.action_seconds > 0:
            time.sleep(self.action_seconds)
        self.state = "idle"
        self.history.append((time.time(), action, "ok"))
        log.info("FakeRobot 完成 %s", action)
        return True, f"已执行 {action}"

    def stop(self) -> Tuple[bool, str]:
        self.state = "stopped"
        self.history.append((time.time(), "stop", "ok"))
        log.info("FakeRobot 停止")
        return True, "已停止"

    @property
    def executed_actions(self) -> List[str]:
        return [a for _, a, _ in self.history]
