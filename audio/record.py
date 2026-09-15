"""录音与播放（PC 麦克风；阶段5 换 G1 麦克风时在这里加后端）。

- record_fixed(seconds)：固定时长录音（第2周的基础功能）
- record_auto()：能量检测自动断句 ——
    * 一直没人说话，等满 silence_timeout → 返回 None（调用方回 IDLE）
    * 说完后静音超过 end_silence → 返回这句话的音频
    * 总时长到 max_duration → 截断返回（录音过长自动截断）
- calibrate()：打印环境噪音能量，帮助调 audio.energy_threshold
"""
from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
import sounddevice as sd
import soundfile as sf

from app.config import AudioConfig


def _rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    x = block.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(x * x)))


def _to_mono(block: np.ndarray) -> np.ndarray:
    if block.ndim == 2:
        if block.shape[1] > 1:
            return block.mean(axis=1).astype(np.int16)
        return block[:, 0]
    return block


def resample(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or len(data) == 0:
        return data
    n = int(round(len(data) * dst_sr / src_sr))
    x_old = np.arange(len(data), dtype=np.float64)
    x_new = np.linspace(0, len(data) - 1, n)
    return np.interp(x_new, x_old, data.astype(np.float64)).astype(np.int16)


class Recorder:
    def __init__(self, cfg: AudioConfig, device: Optional[Union[int, str]] = None):
        self.cfg = cfg
        self.device = device if device is not None else cfg.input_device

    # ---------- 设备 ----------

    def _open_stream(self) -> Tuple[sd.InputStream, int]:
        """优先 16k 单声道；设备不支持就用它的默认采样率，录完重采样。"""
        try:
            stream = sd.InputStream(
                samplerate=self.cfg.sample_rate, channels=1,
                dtype="int16", device=self.device,
            )
            return stream, self.cfg.sample_rate
        except Exception:
            dev = self.device if self.device is not None else sd.default.device[0]
            info = sd.query_devices(dev, kind="input")
            sr = int(info["default_samplerate"])
            ch = max(1, int(info["max_input_channels"]))
            stream = sd.InputStream(samplerate=sr, channels=ch, dtype="int16", device=dev)
            return stream, sr

    # ---------- 录音 ----------

    def record_fixed(self, seconds: float) -> np.ndarray:
        """固定时长录音，返回 16k 单声道 int16。"""
        stream, sr = self._open_stream()
        with stream:
            data, _ = stream.read(int(seconds * sr))
        mono = _to_mono(np.array(data)).astype(np.int16)
        return resample(mono, sr, self.cfg.sample_rate)

    def record_auto(self) -> Optional[np.ndarray]:
        """自动断句录音。

        返回 16k 单声道 int16；等待期间一直没有语音则返回 None
        （用于“唤醒后 2~3 秒无后续语音自动回到 IDLE”）。
        """
        c = self.cfg
        stream, sr = self._open_stream()
        block_frames = max(1, int(0.1 * sr))  # 100ms 一块
        blocks: List[np.ndarray] = []
        pre_voice: deque = deque(maxlen=2)    # 说话前保留 0.2s 引子
        speech_started = False
        start = last_voice = time.monotonic()

        with stream:
            while True:
                data, _ = stream.read(block_frames)
                mono = _to_mono(np.array(data)).astype(np.int16)
                now = time.monotonic()
                energy = _rms(mono)

                if not speech_started:
                    if energy >= c.energy_threshold:
                        speech_started = True
                        last_voice = now
                        blocks.extend(pre_voice)
                        blocks.append(mono)
                    else:
                        pre_voice.append(mono)
                        if now - start >= c.silence_timeout:
                            return None  # 没人说话
                else:
                    blocks.append(mono)
                    if energy >= c.energy_threshold:
                        last_voice = now
                    elif now - last_voice >= c.end_silence:
                        break  # 说完一句话
                if blocks and len(blocks) * block_frames / sr >= c.max_duration:
                    break  # 录音过长自动截断

        if not speech_started or not blocks:
            return None
        blocks = self._trim_tail_silence(blocks)
        audio = np.concatenate(blocks)
        audio = resample(audio, sr, c.sample_rate)
        if len(audio) < int(c.min_duration * c.sample_rate):
            return None  # 纯噪音毛刺
        return audio

    def _trim_tail_silence(self, blocks: List[np.ndarray]) -> List[np.ndarray]:
        """去掉结尾超过 ~0.3s 的静音块，减少 ASR 处理量。"""
        quiet_tail = 0
        for b in reversed(blocks):
            if _rms(b) >= self.cfg.energy_threshold:
                break
            quiet_tail += 1
        drop = max(0, quiet_tail - 3)
        return blocks[: len(blocks) - drop] if drop else blocks

    # ---------- 存储 / 播放 ----------

    def save_wav(self, audio: np.ndarray, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(p), audio, self.cfg.sample_rate)
        return p

    @staticmethod
    def play(audio: np.ndarray, sample_rate: int = 16000) -> None:
        sd.play(audio, sample_rate)
        sd.wait()

    @staticmethod
    def play_wav_file(path: Union[str, Path]) -> None:
        data, sr = sf.read(str(path), dtype="int16")
        data = np.asarray(data)
        if data.ndim > 1:
            data = data.mean(axis=1).astype(np.int16)
        Recorder.play(data, sr)

    # ---------- 调试 ----------

    def calibrate(self, seconds: float = 4.0) -> None:
        """打印环境音量条，帮助确定 energy_threshold。"""
        print(f"请在 {seconds:.0f} 秒内保持安静，然后再正常说两句话……")
        stream, sr = self._open_stream()
        block_frames = max(1, int(0.1 * sr))
        levels = []
        with stream:
            n = int(seconds * 10)
            for i in range(n):
                data, _ = stream.read(block_frames)
                e = _rms(_to_mono(np.array(data)).astype(np.int16))
                levels.append(e)
                bar = "#" * min(60, int(e * 500))
                print(f"  {i * 0.1:4.1f}s  rms={e:.4f} {bar}")
        quiet = sorted(levels)[: len(levels) // 3]
        noise = sum(quiet) / max(1, len(quiet))
        print(f"\n环境噪音约 {noise:.4f}；说话时应明显更高。")
        print(f"建议把 audio.energy_threshold 设为噪音的 2~3 倍，例如 {max(0.01, noise * 2.5):.3f}")
