"""settings.yaml 与代码契约的一致性。"""
from app.config import Settings


def test_load_repo_yaml(settings):
    assert settings.app.mode in ("chat", "assistant")
    # 白名单、确认、冷却（README 安全规范）
    assert set(settings.actions.whitelist) == {"stand", "sit", "wave", "stop"}
    assert "stop" not in settings.actions.confirm_required   # stop 永远直通
    assert settings.actions.cooldown >= 3.0
    # 唤醒词与同音字
    assert "小宇" in settings.wake.words
    assert len(settings.wake.words) >= 2


def test_defaults_when_file_missing(tmp_path):
    s = Settings.load(tmp_path / "not_exist.yaml")
    assert s.actions.whitelist == ["stand", "sit", "wave", "stop"]
    assert s.audio.sample_rate == 16000


def test_asr_sample_rate_matches_audio(settings):
    """回归：asr.py 曾引用 ASRConfig 上不存在的 sample_rate 导致识别全挂
    （冒烟测试走的是文件路径分支，没暴露；真实流程传数组才炸）。"""
    from app.config import ASRConfig

    assert hasattr(ASRConfig(), "sample_rate")     # 字段必须存在
    # build_audio 负责把两者同步，缺一不可
    from app.main import build_audio

    recorder, asr, _ = build_audio(settings)
    assert asr.cfg.sample_rate == recorder.cfg.sample_rate
