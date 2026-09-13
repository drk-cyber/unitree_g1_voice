"""阶段1 主程序。

在仓库根目录运行：
  python -m app.main                     # assistant 模式（第3周完整流程）
  python -m app.main --mode chat         # 第2周对话原型：说话 → 识别 → 回答 → 播报
  python -m app.main --rules             # 不用 Ollama，规则解析（没装大模型时先跑通）
  python -m app.main --once              # 只处理一句话就退出（冒烟测试）
  python -m app.main --calibrate-mic     # 测环境噪音，调 energy_threshold
  python -m app.main --list-devices      # 列出音频设备
  python -m app.main --no-confirm        # 跳过执行前确认（调试用）
"""
from __future__ import annotations

import argparse
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from app.config import Settings
from app.state import State, StateMachine


def setup_logging(log_dir: str) -> None:
    root = logging.getLogger("g1")
    root.setLevel(logging.INFO)
    if root.handlers:          # 防重复初始化
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fh = TimedRotatingFileHandler(
        Path(log_dir) / "assistant.log", when="midnight", backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    # 命令流水单独一份：时间 | 原文 | intent | 结果（安全规范第8条）
    audit = logging.getLogger("g1.audit")
    ah = TimedRotatingFileHandler(
        Path(log_dir) / "commands.log", when="midnight", backupCount=14, encoding="utf-8")
    ah.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    audit.addHandler(ah)
    audit.propagate = False


def build_audio(settings: Settings):
    from audio.record import Recorder
    from audio.asr import SenseVoiceASR
    from audio.tts import ConsoleTTS, EdgeTTS

    # 识别配置的采样率必须和录音一致（录音模块统一输出 audio.sample_rate）
    settings.asr.sample_rate = settings.audio.sample_rate
    recorder = Recorder(settings.audio)
    asr = SenseVoiceASR(settings.asr)
    tts = EdgeTTS(settings.tts) if settings.tts.engine == "edge" else ConsoleTTS(settings.tts)
    return recorder, asr, tts


def build_brain(settings: Settings):
    from llm.intent_parser import OllamaIntentParser, RuleBasedParser
    from robot.control_service import SafetyLayer
    from robot.fake_robot import FakeRobot

    if settings.llm.backend == "rules":
        parser = RuleBasedParser()
    else:
        parser = OllamaIntentParser(settings.llm)
    robot = FakeRobot(action_seconds=settings.app.fake_action_seconds)
    safety = SafetyLayer(
        robot, settings.actions.whitelist, cooldown=settings.actions.cooldown)
    return parser, robot, safety


def make_record_text(recorder, asr):
    """确认环节：录一句 → 识别 → 返回文本。"""
    def record_text() -> Optional[str]:
        audio = recorder.record_auto()
        if audio is None:
            return None
        text = asr.transcribe(audio)
        print(f"[确认答复] {text}")
        return text
    return record_text


def _maybe_save_utterance(settings: Settings, recorder, audio, utter_dir) -> None:
    if utter_dir is not None:
        recorder.save_wav(audio, utter_dir / f"{time.strftime('%H%M%S')}.wav")


# ---------------- 第2周：对话原型 ----------------

def run_chat_mode(settings: Settings, once: bool = False) -> None:
    from llm.chat import OllamaChat

    recorder, asr, tts = build_audio(settings)
    chat = OllamaChat(settings.llm)
    print("=" * 46)
    print("小宇对话原型（第2周：说话 → 识别 → 回答 → 播报）")
    print("  说话就行，不需要唤醒词。Ctrl+C 退出")
    print("=" * 46)
    print("正在加载语音识别模型（首次运行需下载，请耐心等待）……")
    asr.load()
    print("模型就绪，开始倾听。")
    while True:
        try:
            audio = recorder.record_auto()
            if audio is None:
                continue
            text = asr.transcribe(audio)
            if not text.strip():
                print("[你] （没听清，请再说一遍）")
                continue
            print(f"[你] {text}")
            reply = chat.reply(text)
            if reply is None:
                tts.speak("我的大脑暂时不在线，请确认 Ollama 已经运行。")
            else:
                print(f"[小宇] {reply}")
                tts.speak(reply)
            if once:
                break
        except KeyboardInterrupt:
            print("\n[退出] 再见！")
            break
        except Exception as e:
            logging.getLogger("g1.main").exception("主循环异常（忽略，继续）：%s", e)
            if once:
                break


# ---------------- 第3周：完整助手流程 ----------------

def run_assistant_mode(settings: Settings, once: bool = False) -> None:
    from app.assistant import TurnOutcome, VoiceAssistant

    recorder, asr, tts = build_audio(settings)
    parser, robot, safety = build_brain(settings)
    assistant = VoiceAssistant(
        tts=tts, parser=parser, robot=robot, safety=safety,
        settings=settings, record_text=make_record_text(recorder, asr))
    sm = StateMachine(listen_timeout=settings.audio.silence_timeout)

    print("=" * 46)
    print("小宇语音助手（第3周：唤醒 → 意图 → 安全层 → 执行）")
    print("  唤醒词：小宇（小雨 / 小语 / 小余 也可以）")
    print("  试试：小宇，挥手 / 小宇，站起来 / 小宇，坐下")
    print("  任何时候喊“停止”立即停下。Ctrl+C 退出")
    print("=" * 46)
    print("正在加载语音识别模型（首次运行需下载，请耐心等待）……")
    asr.load()
    print("模型就绪，开始倾听。")

    utter_dir = None
    if settings.app.save_utterances:
        utter_dir = Path(settings.app.log_dir) / "utterances"

    while True:
        try:
            if sm.state is State.IDLE:
                audio = recorder.record_auto()
                if audio is None:
                    continue                      # 没人说话，继续待命
                _maybe_save_utterance(settings, recorder, audio, utter_dir)
                text = asr.transcribe(audio)
                if not text.strip():
                    print("[识别] （没听清，请再说一遍）")
                    continue
                print(f"[识别] {text}")
                sm.command()                      # → PROCESSING
                outcome = assistant.handle_text(text)
                sm.done()                         # → IDLE
                if outcome is TurnOutcome.WAKE_LISTENING and sm.wake():
                    print("[状态] 已唤醒，请说指令……")
                if once:
                    break

            elif sm.state is State.LISTENING:
                audio = recorder.record_auto()
                # record_auto 等不到语音自己会返回 None（silence_timeout），
                # 这里不能再用“距唤醒是否超时”丢弃已录到的指令
                if audio is None:
                    if sm.timeout():
                        print("[状态] 没听到指令，继续待命。")
                    if once:
                        break
                    continue
                _maybe_save_utterance(settings, recorder, audio, utter_dir)
                text = asr.transcribe(audio)
                if not text.strip():
                    print("[识别] （没听清，请再说一遍）")
                    continue
                print(f"[识别] {text}")
                sm.command()                      # → PROCESSING
                assistant.handle_text(text, in_listening=True)
                sm.done()                         # → IDLE
                if once:
                    break

        except KeyboardInterrupt:
            print("\n[退出] 再见！")
            break
        except Exception as e:                    # 验收：全程程序不退出
            logging.getLogger("g1.main").exception("主循环异常（已恢复，继续运行）：%s", e)
            sm.reset()
            if once:
                break


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="G1 语音控制 阶段1 原型")
    ap.add_argument("--config", default="config/settings.yaml")
    ap.add_argument("--mode", choices=["chat", "assistant"], default=None,
                    help="覆盖 settings 里的 app.mode")
    ap.add_argument("--rules", action="store_true", help="不用 Ollama，规则解析")
    ap.add_argument("--no-confirm", action="store_true", help="跳过执行前语音确认")
    ap.add_argument("--once", action="store_true", help="只处理一句话")
    ap.add_argument("--calibrate-mic", action="store_true", help="测量环境噪音能量")
    ap.add_argument("--list-devices", action="store_true", help="列出音频设备")
    args = ap.parse_args(argv)

    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        return

    settings = Settings.load(args.config)
    if args.mode:
        settings.app.mode = args.mode
    if args.rules:
        settings.llm.backend = "rules"
    if args.no_confirm:
        settings.actions.confirm_required = []
    setup_logging(settings.app.log_dir)

    if args.calibrate_mic:
        from audio.record import Recorder
        Recorder(settings.audio).calibrate()
        return

    try:
        if settings.app.mode == "chat":
            run_chat_mode(settings, once=args.once)
        else:
            run_assistant_mode(settings, once=args.once)
    except KeyboardInterrupt:
        print("\n[退出] 再见！")


if __name__ == "__main__":
    main()
