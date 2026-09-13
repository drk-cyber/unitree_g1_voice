"""阶段3 实现：Windows 大脑 → Jetson 安全层的 JSON 指令客户端。

阶段1/2 用 FakeRobot + SafetyLayer 本地闭环，还用不到网络。
协议（README 阶段3）：
  请求  {"action": "wave", "request_id": "20260912-001", "source": "voice"}
  响应  {"ok": true, "action": "wave", "state": "executing"}
"""


class JetsonClient:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("阶段3 接入：届时向 Jetson 的 control_service 发 JSON")
