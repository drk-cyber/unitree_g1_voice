"""安全层：白名单、冷却、stop 最高优先级（第3周验收）。"""
import pytest

from robot.control_service import SafetyLayer
from robot.fake_robot import FakeRobot

ALLOWED = ["stand", "sit", "wave", "stop"]


def test_whitelist_rejects_unknown(clock, robot):
    safety = SafetyLayer(robot, ALLOWED, cooldown=3.0, clock=clock)
    d = safety.run("dance")
    assert not d.ok
    assert "白名单" in d.reason
    assert robot.executed_actions == []      # 乱指令不触发任何动作


def test_cooldown_blocks_then_allows(clock, robot):
    safety = SafetyLayer(robot, ALLOWED, cooldown=3.0, clock=clock)
    assert safety.run("wave").ok
    clock.advance(1.0)
    d = safety.run("sit")
    assert not d.ok and "频繁" in d.reason
    clock.advance(2.5)                       # 距上次 3.5 秒
    assert safety.run("sit").ok
    assert robot.executed_actions == ["wave", "sit"]


def test_stop_ignores_cooldown(clock, robot):
    safety = SafetyLayer(robot, ALLOWED, cooldown=3.0, clock=clock)
    assert safety.run("wave").ok
    clock.advance(0.5)                       # 冷却中
    assert safety.request_stop().ok          # stop 永远有效
    assert robot.state == "stopped"


def test_check_does_not_perform(clock, robot):
    safety = SafetyLayer(robot, ALLOWED, cooldown=3.0, clock=clock)
    d = safety.check("wave")
    assert d.ok
    assert robot.executed_actions == []      # 只检查不执行


def test_robot_rejects_unknown_action_directly():
    robot = FakeRobot()
    ok, msg = robot.perform("jump")
    assert not ok
    ok, _ = robot.perform("wave")
    assert ok
    assert robot.executed_actions == ["wave"]
    ok, _ = robot.stop()
    assert ok and robot.state == "stopped"
