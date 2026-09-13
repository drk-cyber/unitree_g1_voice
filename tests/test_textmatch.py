"""唤醒词 / 停止词 / 确认词匹配（第3周验收核心）。"""
from app import textmatch

WAKE = ["小宇", "小雨", "小语", "小余"]
STOP = ["停", "别动", "站住"]
GUARD = ["别停", "不要停", "别停止", "不要停止"]
YES = ["确认", "是的", "好", "好的", "嗯", "可以"]
NO = ["不", "不要", "取消", "别"]


class TestWake:
    def test_wake_with_command(self):
        wake, rest = textmatch.extract_wake("小宇，请挥手", WAKE)
        assert wake == "小宇"
        assert rest == "请挥手"

    def test_homophones(self):
        for w in ("小雨", "小语", "小余"):
            wake, _ = textmatch.extract_wake(f"{w}，挥手", WAKE)
            assert wake == w

    def test_wake_only(self):
        wake, rest = textmatch.extract_wake("小宇", WAKE)
        assert wake == "小宇" and rest == ""

    def test_wake_with_exclamation(self):
        wake, rest = textmatch.extract_wake("小宇！", WAKE)
        assert wake == "小宇" and rest == ""

    def test_no_wake_in_middle(self):
        wake, _ = textmatch.extract_wake("你好小宇，挥手", WAKE)
        assert wake is None

    def test_no_wake_at_all(self):
        wake, rest = textmatch.extract_wake("今天天气怎么样", WAKE)
        assert wake is None and rest == "今天天气怎么样"

    def test_punctuation_after_wake(self):
        wake, rest = textmatch.extract_wake("小宇。站起来。", WAKE)
        assert wake == "小宇" and rest == "站起来。"


class TestStop:
    def test_stop_words(self):
        for t in ("停止", "停下", "停下来", "别动", "站住", "小宇，停止"):
            assert textmatch.contains_stop(t, STOP, GUARD), t

    def test_not_stop(self):
        for t in ("你好", "小宇，请挥手", "今天天气怎么样", ""):
            assert not textmatch.contains_stop(t, STOP, GUARD), t

    def test_negation_guard(self):
        # “不要停下来”不是停止指令
        assert not textmatch.contains_stop("不要停下来", STOP, GUARD)
        assert not textmatch.contains_stop("别停止，继续挥手", STOP, GUARD)


class TestConfirm:
    def test_yes(self):
        for t in ("好的。", "确认", "嗯", "是的", "可以"):
            assert textmatch.is_affirmative(t, YES, NO), t

    def test_no(self):
        for t in ("不要", "取消", "算了", "不可以"):
            assert not textmatch.is_affirmative(t, YES, NO), t

    def test_negative_wins_over_affirmative_substring(self):
        # “不可以”包含“可以”，必须先判否定
        assert not textmatch.is_affirmative("不可以", YES, NO)

    def test_empty(self):
        assert not textmatch.is_affirmative(None, YES, NO)
        assert not textmatch.is_affirmative("", YES, NO)
