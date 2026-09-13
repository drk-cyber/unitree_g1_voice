"""中文语音识别：FunASR + SenseVoice-Small（README 阶段1 第2周）。

funasr 延迟导入：纯逻辑单测 / 规则模式不需要装它。
首次 load() 会从 ModelScope 下载模型（几百 MB），之后走本地缓存。
"""
from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, Union

import numpy as np
import soundfile as sf

from app.config import ASRConfig

log = logging.getLogger("g1.asr")


class SenseVoiceASR:
    def __init__(self, cfg: ASRConfig):
        self.cfg = cfg
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from funasr import AutoModel  # 延迟导入

        log.info("加载识别模型 %s（首次运行需下载，请耐心等待）……", self.cfg.model)
        self._model = AutoModel(
            model=self.cfg.model,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=self.cfg.device,
            disable_update=True,
        )
        log.info("识别模型就绪")

    def transcribe(self, audio: Union[np.ndarray, str, Path, None]) -> str:
        """audio: 16k 单声道 int16 ndarray 或 wav 路径。返回识别文本（失败返回空串，不抛异常）。"""
        if audio is None:
            return ""
        try:
            self.load()
            tmp: Optional[Path] = None
            if isinstance(audio, np.ndarray):
                if audio.size == 0:
                    return ""
                with NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    tmp = Path(f.name)
                sf.write(str(tmp), audio, self.cfg.sample_rate)
                source = str(tmp)
            else:
                source = str(audio)
            try:
                res = self._model.generate(
                    input=source,
                    cache={},
                    language=self.cfg.language,
                    use_itn=True,
                    batch_size_s=60,
                    merge_vad=True,
                    merge_length_s=15,
                )
                raw = res[0]["text"] if res else ""
            finally:
                if tmp is not None and tmp.exists():
                    tmp.unlink()
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            return rich_transcription_postprocess(raw).strip()
        except Exception as e:  # 识别失败不能让主循环退出（验收：全程不退出）
            log.exception("识别失败：%s", e)
            return ""
