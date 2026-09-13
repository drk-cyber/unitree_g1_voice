"""状态机转移与超时（第3周验收：IDLE/LISTENING/PROCESSING）。"""
from app.state import State, StateMachine
from conftest import FakeClock


def test_happy_path_two_step():
    clk = FakeClock()
    sm = StateMachine(listen_timeout=2.5, clock=clk)
    assert sm.state is State.IDLE
    assert sm.wake()                       # “小宇”
    assert sm.state is State.LISTENING
    assert sm.command()                    # 听到指令
    assert sm.state is State.PROCESSING
    assert sm.done()
    assert sm.state is State.IDLE


def test_single_shot_wake_plus_command():
    sm = StateMachine(clock=FakeClock())
    assert sm.command()                    # “小宇，挥手”一句话直达
    assert sm.state is State.PROCESSING
    assert sm.done()


def test_invalid_transitions_rejected():
    sm = StateMachine(clock=FakeClock())
    assert not sm.done()                   # IDLE 不能直接 done
    assert not sm.timeout()                # IDLE 没有“超时回退”这一转移
    sm.wake()
    assert not sm.wake()                   # LISTENING 不能再次 wake
    sm.command()
    assert not sm.command()                # PROCESSING 不能再 command


def test_listen_timeout():
    clk = FakeClock()
    sm = StateMachine(listen_timeout=2.5, clock=clk)
    sm.wake()
    assert not sm.is_listen_expired()
    clk.advance(2.0)
    assert not sm.is_listen_expired()
    clk.advance(0.6)
    assert sm.is_listen_expired()
    assert sm.timeout()
    assert sm.state is State.IDLE


def test_reset_from_any_state():
    sm = StateMachine(clock=FakeClock())
    sm.command()
    sm.reset()
    assert sm.state is State.IDLE
