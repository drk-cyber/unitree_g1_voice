"""安全控制层（README 安全规范；阶段1 离线版，阶段2 搬上 Jetson 常驻）。

规则：
1. 只执行白名单动作，未知一律拒绝；
2. stop 永远允许、优先级最高、可打断，不走冷却；
3. 相邻动作间隔 ≥ cooldown 秒（stop 也计入——刚停完不要马上动）；
4. 每次请求/执行写日志。

阶段2 时把这个类包上网络服务和 unitree SDK 就是 Jetson 侧常驻的
control_service。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

log = logging.getLogger("g1.safety")


@dataclass
class Decision:
    ok: bool
    reason: str = ""


class SafetyLayer:
    def __init__(
        self,
        robot,
        allowed_actions: List[str],
        cooldown: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.robot = robot
        self.allowed = list(allowed_actions)
        self.cooldown = cooldown
        self._clock = clock
        self._last_action_at: Optional[float] = None

    def check(self, action: str) -> Decision:
        """只检查不执行（用于“先确认再执行”的预检）。"""
        if action not in self.allowed:
            return Decision(False, f"{action} 不在白名单")
        if action != "stop" and self._last_action_at is not None:
            elapsed = self._clock() - self._last_action_at
            if elapsed < self.cooldown:
                return Decision(False, f"动作太频繁（还需等 {self.cooldown - elapsed:.1f} 秒）")
        return Decision(True, "允许")

    def run(self, action: str) -> Decision:
        """校验并执行一个动作。"""
        d = self.check(action)
        if not d.ok:
            log.warning("拒绝 %s：%s", action, d.reason)
            return d
        ok, msg = self.robot.perform(action)
        self._last_action_at = self._clock()
        log.info("执行 %s → %s", action, "成功" if ok else f"失败（{msg}）")
        return Decision(ok, msg)

    def request_stop(self) -> Decision:
        """stop 永远允许。"""
        return self.run("stop")
