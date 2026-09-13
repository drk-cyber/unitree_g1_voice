"""无麦克风冒烟测试：edge-tts 合成 → SenseVoice 识别 → （可选）Ollama 意图解析。

验证 ASR / TTS / LLM 三件套都正常，不需要对着麦克风说话：
  python scripts/smoke_test.py            # 全部
  python scripts/smoke_test.py --skip-llm # 只测 TTS + ASR（不装 Ollama 也能跑）
  python scripts/smoke_test.py --no-play  # 不播放声音（安静环境）
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-llm", action="store_true", help="跳过 Ollama 意图解析")
    ap.add_argument("--no-play", action="store_true", help="不播放合成的声音")
    args = ap.parse_args()

    settings = Settings.load(ROOT / "config" / "settings.yaml")
    text = "小宇，请挥手"
    print(f"[1/3] Edge-TTS 合成：“{text}”（需要联网）")
    from audio.tts import EdgeTTS

    tts = EdgeTTS(settings.tts)
    with tempfile.TemporaryDirectory() as td:
        mp3 = Path(td) / "tts.mp3"
        if not tts.synth_to_file(text, mp3):
            print("  [FAIL] edge-tts 合成失败：检查网络")
            return 1

        import miniaudio
        import numpy as np

        dec = miniaudio.decode_file(
            str(mp3), nchannels=1, sample_rate=16000,
            output_format=miniaudio.SampleFormat.SIGNED16)
        # 主流程传给识别的是 int16 数组（不是文件路径），保持同一分支
        pcm = np.asarray(dec.samples, dtype=np.int16)

        if not args.no_play:
            try:
                from audio.record import Recorder
                Recorder.play(pcm, 16000)  # 有耳机就能听到
            except Exception as e:
                print(f"  （跳过试听：{e}）")

        print("[2/3] SenseVoice 识别（首次运行会下载模型，约几百 MB）")
        from audio.asr import SenseVoiceASR

        heard = SenseVoiceASR(settings.asr).transcribe(pcm)
        print(f"  识别结果：{heard}")
        asr_ok = "挥手" in heard
        print(f"  [{'OK' if asr_ok else 'FAIL'}] 关键词“挥手”{'识别成功' if asr_ok else '未识别出'}")

    llm_ok = True
    if not args.skip_llm:
        print("[3/3] Ollama 意图解析")
        from llm.intent_parser import OllamaIntentParser

        r = OllamaIntentParser(settings.llm).parse("请挥手")
        if r is None:
            llm_ok = False
            print("  [FAIL] Ollama 不可用或输出非法（先 ollama pull "
                  f"{settings.llm.ollama.model}）")
        else:
            llm_ok = r.intent.value == "wave"
            print(f"  intent={r.intent.value} reply={r.reply!r} confidence={r.confidence}")
            print(f"  [{'OK' if llm_ok else 'FAIL'}] 意图应为 wave")

    if asr_ok and llm_ok:
        print("\n全部通过：TTS / ASR" + ("" if args.skip_llm else " / LLM") + " 就绪。")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
