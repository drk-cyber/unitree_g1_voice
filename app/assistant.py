"""语音助手编排（README 阶段3 伪代码的阶段1 离线版）。

流程：识别文本 → stop 直通 → 唤醒词 → 意图解析 → 安全层 → FakeRobot → 播报。

设计要点（对应验收标准）：
- “停止”不经过大模型：contains_stop 命中即直接执行 stop；
- 唤醒后的第二句话不需要再喊“小宇”（in_listening=True）；
- 大模型返回乱文本 / 非法 JSON → 降级为 none 或规则解析，绝不放行动作；
- 所有异常都在这一层吞掉，主循环永不退出。

本类不直接接触音频设备：文本从 handle_text() 进，
确认环节通过注入的 record_text()（录音+识别）拿用户答复，方便单测全流程。
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Optional

from app import textmatch
from app.config import Settings
from app.schemas import Intent, IntentResult
from llm.intent_parser import RuleBasedParser
from robot.control_service import SafetyLayer
from robot.fake_robot import FakeRobot

log = logging.getLogger("g1.assistant")
audit = logging.getLogger("g1.audit")  # 命令流水：时间、识别原文、intent、执行结果


class TurnOutcome(str, Enum):
    IGNORED = "ignored"          # 没有唤醒词，忽略
    WAKE_LISTENING = "wake"      # 只听到唤醒词，等下一句指令
    COMPLETED = "completed"      # 一轮处理完成（执行 / 取消 / 闲聊 / 拒绝）
    STOPPED = "stopped"          # 停止指令已执行


class VoiceAssistant:
    def __init__(
        self,
        tts,
        parser,
        robot: FakeRobot,
        safety: SafetyLayer,
        settings: Settings,
        record_text: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.tts = tts
        self.parser = parser
        self.robot = robot
        self.safety = safety
        self.cfg = settings
        self._record_text = record_text
        self._rules = RuleBasedParser() if settings.llm.fallback_to_rules else None

    # ---------------- 对外入口 ----------------

    def handle_text(self, text: str, *, in_listening: bool = False) -> TurnOutcome:
        """处理一句识别文本。in_listening=True 表示这是唤醒后的第二句。"""
        text = (text or "").strip()
        if not text:
            return TurnOutcome.IGNORED
        log.info("识别文本：%r（in_listening=%s）", text, in_listening)

        # 1) stop 直通：不经过大模型、不需要唤醒词、不需要确认（安全规范第1条）
        if textmatch.contains_stop(text, self.cfg.stop.words, self.cfg.stop.guard_words):
            return self._stop_now(text)

        # 2) 唤醒词判断
        wake, rest = textmatch.extract_wake(text, self.cfg.wake.words)
        if wake is not None:
            command = rest
        elif in_listening:
            command = text               # 唤醒后的第二句不用再喊“小宇”
        elif not self.cfg.wake.require_wake:
            command = text               # 调试模式：免唤醒
        else:
            log.info("无唤醒词，忽略")
            audit.info("text=%r | intent=- | result=ignored", text)
            return TurnOutcome.IGNORED

        if not command:
            return TurnOutcome.WAKE_LISTENING   # 只说了“小宇”

        # 3) + 4) 意图解析与派发
        intent = self._parse(command)
        return self._dispatch(intent, text)

    # ---------------- 内部流程 ----------------

    def _stop_now(self, text: str) -> TurnOutcome:
        d = self.safety.run("stop")
        self._speak("好的，立即停止。" if d.ok else f"停止失败：{d.reason}")
        audit.info("text=%r | intent=stop | result=%s", text, "executed" if d.ok else "denied")
        return TurnOutcome.STOPPED

    def _parse(self, command: str) -> IntentResult:
        """意图解析。任何失败都安全降级，绝不抛异常、绝不放行未知动作。"""
        try:
            result = self.parser.parse(command)
        except Exception as e:
            log.warning("意图解析异常：%s", e)
            result = None
        if result is None:
            if self._rules is not None:
                log.warning("大模型不可用/输出非法，退回规则解析")
                result = self._rules.parse(command)
            else:
                result = IntentResult(
                    intent=Intent.NONE, reply="我暂时没听懂，请再说一遍。", confidence=0.0)
        audit.info("command=%r | intent=%s | confidence=%.2f",
                   command, result.intent.value, result.confidence)
        return result

    def _dispatch(self, intent: IntentResult, raw_text: str) -> TurnOutcome:
        names = self.cfg.actions.chinese_names

        if intent.intent is Intent.NONE:
            self._speak(intent.reply or "我暂时不会执行这个指令。")
            audit.info("text=%r | intent=none | result=chat", raw_text)
            return TurnOutcome.COMPLETED

        if intent.intent is Intent.STOP:
            return self._stop_now(raw_text)   # 双保险：解析出 stop 也不确认

        action = intent.intent.value
        cn = names.get(action, action)

        # 安全层预检（白名单 + 冷却）在确认之前，避免确认了又拒绝
        pre = self.safety.check(action)
        if not pre.ok:
            self._speak(f"现在不能执行{cn}：{pre.reason}。")
            audit.info("text=%r | intent=%s | result=denied(%s)", raw_text, action, pre.reason)
            return TurnOutcome.COMPLETED

        # 语音确认（安全规范第3条；stop 不走这里）
        if action in self.cfg.actions.confirm_required:
            self._speak(f"即将执行{cn}，确认吗？")
            answer = self._ask_confirm()
            if answer is None:
                self._speak("没有听到答复，已取消。")
                audit.info("text=%r | intent=%s | result=cancelled(no-answer)", raw_text, action)
                return TurnOutcome.COMPLETED
            if not textmatch.is_affirmative(
                    answer, self.cfg.confirm.words_yes, self.cfg.confirm.words_no):
                self._speak("好的，已取消。")
                audit.info("text=%r | intent=%s | result=cancelled", raw_text, action)
                return TurnOutcome.COMPLETED

        d = self.safety.run(action)
        if d.ok:
            self._speak(intent.reply or f"好的，我来执行{cn}。")
        else:
            self._speak(f"执行失败：{d.reason}。")
        audit.info("text=%r | intent=%s | result=%s",
                   raw_text, action, "executed" if d.ok else "denied")
        return TurnOutcome.COMPLETED

    # ---------------- 工具 ----------------

    def _ask_confirm(self) -> Optional[str]:
        if self._record_text is None:
            return None
        try:
            return self._record_text()
        except Exception as e:
            log.warning("确认录音失败：%s", e)
            return None

    def _speak(self, text: str) -> None:
        try:
            self.tts.speak(text)
        except Exception as e:
            log.warning("播报失败（已忽略，继续运行）：%s", e)
