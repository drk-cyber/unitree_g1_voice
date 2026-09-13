"""VoiceAssistant 全流程（对应第3周验收标准，全部用假组件）。

验收映射：
- “小宇，请挥手” → intent=wave 并请求确认
- “停止”不经过大模型，直接返回 stop
- “跳起来” → none；闲聊 → none
- 模型返回乱文本 / 非法 JSON 时不执行任何动作，程序不崩溃
"""
from app.assistant import TurnOutcome
from app.schemas import Intent, IntentResult
from conftest import BoomTTS, ScriptedParser, SpyTTS


def wave_result():
    return IntentResult(intent=Intent.WAVE, reply="好的，我来挥手。", confidence=0.9)


# ---------- 验收 1：唤醒 + 挥手 + 确认 ----------

def test_wake_wave_confirm_flow(make_assistant):
    ctx = make_assistant(
        ScriptedParser(wave_result()), confirm_answers=["好的"])
    out = ctx.assistant.handle_text("小宇，请挥手")
    assert out is TurnOutcome.COMPLETED
    assert "即将执行挥手，确认吗？" in ctx.tts.spoken[0]     # 请求确认
    assert ctx.robot.executed_actions == ["wave"]            # 确认后执行
    assert "好的，我来挥手。" in ctx.tts.spoken               # 播报模型回复


def test_confirm_rejected_cancels(make_assistant):
    ctx = make_assistant(ScriptedParser(wave_result()), confirm_answers=["不要"])
    out = ctx.assistant.handle_text("小宇，请挥手")
    assert out is TurnOutcome.COMPLETED
    assert ctx.robot.executed_actions == []                  # 未执行
    assert any("已取消" in s for s in ctx.tts.spoken)


def test_confirm_no_answer_cancels(make_assistant):
    ctx = make_assistant(ScriptedParser(wave_result()), confirm_answers=[])
    ctx.assistant.handle_text("小宇，请挥手")
    assert ctx.robot.executed_actions == []
    assert any("没有听到答复" in s for s in ctx.tts.spoken)


# ---------- 验收 2：stop 直通，不经过大模型 ----------

def test_stop_bypasses_llm(make_assistant):
    # 解析器一被调用就炸 → 证明 stop 路径根本没碰大模型
    ctx = make_assistant(ScriptedParser(RuntimeError("大模型不应被调用")))
    out = ctx.assistant.handle_text("停止")
    assert out is TurnOutcome.STOPPED
    assert ctx.robot.executed_actions == ["stop"]
    assert ctx.robot.state == "stopped"
    assert ctx.recorder.used == []                          # stop 不需要确认
    assert ctx.assistant.parser.calls == []                  # 且没调用大模型


def test_stop_with_wake_word_also_direct(make_assistant):
    ctx = make_assistant(ScriptedParser(RuntimeError("不应调用大模型")))
    assert ctx.assistant.handle_text("小宇，停止") is TurnOutcome.STOPPED
    assert ctx.robot.executed_actions == ["stop"]


def test_stop_still_works_during_cooldown(make_assistant):
    ctx = make_assistant(ScriptedParser(RuntimeError()))
    ctx.safety.run("wave")
    ctx.clock.advance(0.5)                                   # 还在冷却期
    assert ctx.assistant.handle_text("别动") is TurnOutcome.STOPPED
    assert ctx.robot.executed_actions == ["wave", "stop"]


# ---------- 验收 3：不会做的动作 / 闲聊 → none ----------

def test_unsupported_action_returns_none(make_assistant):
    ctx = make_assistant(
        ScriptedParser(IntentResult(intent=Intent.NONE, reply="我暂时不会跳起来。")))
    out = ctx.assistant.handle_text("小宇，跳起来")
    assert out is TurnOutcome.COMPLETED
    assert ctx.robot.executed_actions == []                  # 没有任何动作
    assert "我暂时不会跳起来。" in ctx.tts.spoken


def test_chat_returns_none(make_assistant):
    ctx = make_assistant(
        ScriptedParser(IntentResult(intent=Intent.NONE, reply="你好！我在呢。")))
    ctx.assistant.handle_text("小宇，你好")
    assert ctx.robot.executed_actions == []
    assert "你好！我在呢。" in ctx.tts.spoken


# ---------- 验收 4：模型乱输出不执行动作、不崩溃 ----------

def test_llm_garbage_falls_back_to_rules(make_assistant):
    # 模型返回 None（乱文本/非法 JSON/连不上）→ 自动退回规则解析
    ctx = make_assistant(ScriptedParser(None), confirm_answers=["好的"])
    out = ctx.assistant.handle_text("小宇，站起来")
    assert out is TurnOutcome.COMPLETED
    assert ctx.robot.executed_actions == ["stand"]           # 规则解析救回来


def test_llm_garbage_without_fallback_is_safe(make_assistant):
    ctx = make_assistant(ScriptedParser(None), fallback_rules=False)
    out = ctx.assistant.handle_text("小宇，挥手")
    assert out is TurnOutcome.COMPLETED                      # 不崩溃
    assert ctx.robot.executed_actions == []                  # 不执行任何动作


def test_llm_exception_is_safe(make_assistant):
    ctx = make_assistant(ScriptedParser(RuntimeError("ollama 崩了")), fallback_rules=False)
    out = ctx.assistant.handle_text("小宇，挥手")
    assert out is TurnOutcome.COMPLETED
    assert ctx.robot.executed_actions == []


def test_tts_failure_does_not_crash(make_assistant):
    ctx = make_assistant(ScriptedParser(wave_result()),
                         tts=BoomTTS(), confirm_answers=["好的"])
    out = ctx.assistant.handle_text("小宇，请挥手")
    assert out is TurnOutcome.COMPLETED                      # 播报挂了也继续
    assert ctx.robot.executed_actions == ["wave"]


# ---------- 唤醒词行为 ----------

def test_wake_only_then_command_next_utterance(make_assistant):
    ctx = make_assistant(ScriptedParser(wave_result()), confirm_answers=["好的"])
    assert ctx.assistant.handle_text("小宇") is TurnOutcome.WAKE_LISTENING
    assert ctx.robot.executed_actions == []
    # 第二句不需要再喊“小宇”
    assert ctx.assistant.handle_text("挥挥手", in_listening=True) is TurnOutcome.COMPLETED
    assert ctx.robot.executed_actions == ["wave"]


def test_text_without_wake_is_ignored(make_assistant):
    ctx = make_assistant(ScriptedParser(RuntimeError("不应调用大模型")))
    assert ctx.assistant.handle_text("今天天气真好") is TurnOutcome.IGNORED
    assert ctx.assistant.parser.calls == []                  # 大模型都没被叫
    assert ctx.robot.executed_actions == []


def test_punctuation_after_wake(make_assistant):
    ctx = make_assistant(ScriptedParser(wave_result()), confirm_answers=["好的"])
    ctx.assistant.handle_text("小宇！请挥手。")
    assert ctx.assistant.parser.calls == ["请挥手。"]         # 唤醒词和标点被剥掉


# ---------- 冷却 ----------

def test_cooldown_denied_before_confirm(make_assistant):
    ctx = make_assistant(
        ScriptedParser(IntentResult(intent=Intent.SIT, reply="好的，我来坐下。")),
        confirm_answers=["好的"])
    ctx.safety.run("wave")                                   # 3 秒冷却开始
    ctx.clock.advance(1.0)
    ctx.assistant.handle_text("小宇，坐下")
    assert ctx.robot.executed_actions == ["wave"]            # sit 被冷却拦下
    assert any("频繁" in s for s in ctx.tts.spoken)
    assert ctx.recorder.used == []                           # 冷却期连确认都没问
