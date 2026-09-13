"""pytest 公共设施：假组件 + 工厂。

测试用 ScriptedParser / SpyTTS / ScriptedRecord 代替真实
ASR / Ollama / TTS / 麦克风，全流程不需要音频设备和网络。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.assistant import VoiceAssistant
from app.config import Settings
from app.schemas import Intent, IntentResult
from robot.control_service import SafetyLayer
from robot.fake_robot import FakeRobot

REPO = Path(__file__).resolve().parent.parent


class SpyTTS:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)


class BoomTTS(SpyTTS):
    def speak(self, text):
        raise RuntimeError("TTS 挂了")


class ScriptedParser:
    """按脚本依次返回。脚本项：IntentResult / Exception（抛出）/ None（模型不可用）。"""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def parse(self, text):
        self.calls.append(text)
        if not self.script:
            return IntentResult(intent=Intent.NONE)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self, t: float = 100.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class ScriptedRecord:
    """确认环节的假麦克风：按脚本返回识别文本。"""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.used = []

    def __call__(self):
        a = self.answers.pop(0) if self.answers else None
        self.used.append(a)
        return a


@pytest.fixture()
def settings() -> Settings:
    """加载仓库里真实的 settings.yaml —— 顺带验证配置文件合法、与代码契约一致。"""
    return Settings.load(REPO / "config" / "settings.yaml")


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture()
def robot() -> FakeRobot:
    return FakeRobot()


@pytest.fixture()
def safety(robot, settings, clock) -> SafetyLayer:
    return SafetyLayer(
        robot, settings.actions.whitelist,
        cooldown=settings.actions.cooldown, clock=clock)


@pytest.fixture()
def make_assistant(settings):
    """工厂：返回 (assistant, robot, safety, clock, recorder) 打包的命名空间。"""

    def _make(parser, tts=None, *, confirm_answers=(), fallback_rules=None):
        s = settings.model_copy(deep=True)
        if fallback_rules is not None:
            s.llm.fallback_to_rules = fallback_rules
        clk = FakeClock()
        bot = FakeRobot()
        lay = SafetyLayer(
            bot, s.actions.whitelist, cooldown=s.actions.cooldown, clock=clk)
        rec = ScriptedRecord(*confirm_answers)
        tts_obj = tts if tts is not None else SpyTTS()
        va = VoiceAssistant(
            tts=tts_obj, parser=parser, robot=bot, safety=lay,
            settings=s, record_text=rec)
        return SimpleNamespace(
            assistant=va, robot=bot, safety=lay, clock=clk,
            recorder=rec, tts=tts_obj, settings=s)

    return _make
