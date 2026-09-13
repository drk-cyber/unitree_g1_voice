"""配置加载：config/settings.yaml → Settings（pydantic 强类型校验）。

yaml 里没写的字段用这里的默认值，方便只覆盖想改的项。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict


class _Cfg(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AppConfig(_Cfg):
    mode: str = "assistant"            # chat | assistant
    log_dir: str = "logs"
    fake_action_seconds: float = 0.5   # FakeRobot 模拟动作耗时（秒）
    save_utterances: bool = False      # 保存每句录音到 logs/utterances（调试用）


class AudioConfig(_Cfg):
    sample_rate: int = 16000           # ASR 要求 16k
    input_device: Optional[Union[int, str]] = None
    silence_timeout: float = 2.5       # 唤醒后无语音 → 回 IDLE
    end_silence: float = 1.2           # 说完后的静音判定（自动断句）
    max_duration: float = 10.0         # 单次录音上限，超过自动截断
    min_duration: float = 0.2          # 过短的音频当噪音丢弃
    energy_threshold: float = 0.02     # 语音能量阈值（RMS 0~1）


class WakeConfig(_Cfg):
    require_wake: bool = True
    words: list[str] = ["小宇", "小雨", "小语", "小余"]


class StopConfig(_Cfg):
    words: list[str] = ["停", "别动", "站住"]
    guard_words: list[str] = ["别停", "不要停", "别停止", "不要停止"]


class ConfirmConfig(_Cfg):
    words_yes: list[str] = [
        "确认", "确定", "是的", "是", "对", "没错",
        "好", "好的", "嗯", "嗯嗯", "可以", "执行", "ok", "OK",
    ]
    words_no: list[str] = ["不", "不要", "不行", "不可以", "取消", "算了", "别"]


class OllamaConfig(_Cfg):
    host: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:3b"
    timeout: float = 20.0
    temperature: float = 0.1


class LLMConfig(_Cfg):
    backend: str = "ollama"            # ollama | rules
    fallback_to_rules: bool = True
    ollama: OllamaConfig = OllamaConfig()


class ActionConfig(_Cfg):
    whitelist: list[str] = ["stand", "sit", "wave", "stop"]
    confirm_required: list[str] = ["stand", "sit", "wave"]
    cooldown: float = 3.0
    chinese_names: dict[str, str] = {
        "stand": "站立", "sit": "坐下", "wave": "挥手", "stop": "停止",
    }


class EdgeConfig(_Cfg):
    voice: str = "zh-CN-XiaoxiaoNeural"
    rate: str = "+0%"


class TTSConfig(_Cfg):
    engine: str = "edge"               # edge | console
    speak_pause: float = 0.2
    edge: EdgeConfig = EdgeConfig()


class ASRConfig(_Cfg):
    model: str = "iic/SenseVoiceSmall"
    device: str = "cpu"                # cpu | cuda:0
    language: str = "zh"
    sample_rate: int = 16000           # 录入音频的采样率；build_audio 会自动同步成 audio.sample_rate


class Settings(_Cfg):
    app: AppConfig = AppConfig()
    audio: AudioConfig = AudioConfig()
    wake: WakeConfig = WakeConfig()
    stop: StopConfig = StopConfig()
    confirm: ConfirmConfig = ConfirmConfig()
    llm: LLMConfig = LLMConfig()
    actions: ActionConfig = ActionConfig()
    tts: TTSConfig = TTSConfig()
    asr: ASRConfig = ASRConfig()

    @classmethod
    def load(cls, path: Union[str, Path] = "config/settings.yaml") -> "Settings":
        p = Path(path)
        data: dict = {}
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(**data)
