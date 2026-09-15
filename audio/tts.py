"""语音合成（README 阶段1：edge-tts；阶段4 Jetson 上换 Piper 离线版）。

edge-tts 输出 mp3，用 miniaudio 解码成 16k PCM 后交给 sounddevice 播放。
合成/播放任何失败都只打日志，绝不让主循环崩溃。
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Union

from app.config import TTSConfig

log = logging.getLogger("g1.tts")


def play_mp3(path: Union[str, Path]) -> None:
    """解码 mp3 → 16k 单声道 → 走系统默认输出播放（阻塞直到播完）。"""
    import miniaudio
    import numpy as np
    import sounddevice as sd

    dec = miniaudio.decode_file(
        str(path), nchannels=1, sample_rate=16000,
        output_format=miniaudio.SampleFormat.SIGNED16,
    )
    samples = np.asarray(dec.samples, dtype=np.int16)
    sd.play(samples, 16000)
    sd.wait()


class EdgeTTS:
    def __init__(self, cfg: TTSConfig):
        self.cfg = cfg

    def synth_to_file(self, text: str, path: Union[str, Path]) -> bool:
        try:
            import edge_tts

            async def _run() -> None:
                cm = edge_tts.Communicate(text, self.cfg.edge.voice, rate=self.cfg.edge.rate)
                await cm.save(str(path))

            asyncio.run(_run())
            return True
        except Exception as e:
            log.warning("edge-tts 合成失败（检查网络）：%s", e)
            return False

    def speak(self, text: str) -> None:
        if not text:
            return
        print(f"[播报] {text}")
        try:
            with NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp = Path(f.name)
            try:
                if self.synth_to_file(text, tmp):
                    play_mp3(tmp)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as e:
            log.warning("播放失败（检查音箱/输出设备）：%s", e)
        time.sleep(self.cfg.speak_pause)


class ConsoleTTS:
    """无音频设备/联调时的兜底：只打印不出声。"""

    def __init__(self, cfg: Optional[TTSConfig] = None):
        self.cfg = cfg

    def speak(self, text: str) -> None:
        print(f"[播报] {text}")


class PiperTTS:
    """阶段4 在 Jetson 上启用（完全离线，约 100MB）。"""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError("Piper 在阶段4（大脑迁移 Jetson）时接入")
