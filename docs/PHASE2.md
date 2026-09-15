# 阶段 2 运行手册：Jetson 就绪 + G1 键盘控制（第 4～5 周）

> 对应 README《六、阶段 2》。核心思路：**阶段 1 的 SafetyLayer 一行不改**，
> 阶段 2 只做两件事——给"动作"换上真机器人（G1Robot 适配器），把服务搬到 Jetson。
>
> ⚠️ 本阶段开始碰真机。每次上电前过一遍文末安全清单。

## 0. 开始前的检查（对应阶段 0，没做过先补）

| 待确认项 | 怎么查 | 在哪记录 |
|---|---|---|
| Jetson 型号 / 内存 | Jetson 上 `cat /proc/device-tree/model`、`free -h` | 下表 |
| JetPack / 系统 Python | `cat /etc/nv_tegra_release`、`python3 --version` | 下表 |
| 磁盘剩余 / IP / SSH 账号 | `df -h`、`ip addr`（宇树文档给的默认账号） | 下表 |
| Unitree SDK 版本 | `pip show unitree-sdk2py` | 下表 |
| 官方内置动作接口 | 见本文 2.3，逐个实测 | 下表 |
| 急停方式 | 遥控器/按钮，**实际演练一次** | 下表 |

| 待确认项 | 结果 |
|---|---|
| Jetson 型号 / 内存 | 16GB（2026-09-13 用户确认；具体型号上电后 `cat /proc/device-tree/model` 补记） |
| JetPack 版本 / 系统 Python | JetPack 5.x / Ubuntu 20.04（出厂带 ROS2 Foxy）/ **Python 3.8** |
| 磁盘剩余 / IP / SSH 账号 | 2TB 硬盘；IP / SSH 账号上电后补 |
| SDK 版本 | |
| stand / sit / wave / stop 的 SDK 调用 | |
| 急停方式 | |

已确认信息的推论（2026-09-13）：

- **统一内存**：Jetson 的"16G 显存 + 16G 内存"是同一块内存，算预算时
  系统 + SenseVoice + Qwen + Piper 加在一起；16GB 属于 README"推荐配"，
  Qwen2.5-3B 从容，温度可控时可试 7B 4-bit。
- **代码已做 Python 3.8 兼容**（2026-09-13 完成）：类型标注全部改用
  `typing.List/Dict/Tuple`（pydantic 在运行时求值注解，3.8 不认 `list[str]`），
  `pyproject.toml` 的 `requires-python` 改为 `>=3.8`，63 个测试仍全绿。
- **出厂 ROS2 Foxy 不要动**：项目走 unitree_sdk2（DDS），不依赖 ROS。
  不要 apt 大版本升级、不要动系统 Python，一律用 venv 隔离。
- **Ollama 官方支持 JetPack 5**；模型用我们验证过的离线导入方案
  （`scripts/import_qwen_ollama.py`），不依赖 registry.ollama.org。
- torch 到时候要装 NVIDIA 的 Jetson 专用 aarch64 轮子（PyPI 的不带 Jetson CUDA）；
  装不动就走 README 附录 D 的 sherpa-onnx 备选。

## 1. 网络拓扑（第 4 周第一天）

```text
你的电脑 ──(网线/WiFi，按宇树文档)── G1 本体交换机 ── 机载 Jetson
              网段通常是 192.168.123.x
```

- 给电脑网卡配静态 IP（同网段，如 192.168.123.50，具体以宇树文档为准）；
- 找到 Jetson 的 IP 后：`ssh <账号>@<jetson_ip>`；
- 顺手装好 VS Code 的 Remote-SSH 插件——阶段 4 全程靠它开发。

## 2. 第 4 周：环境 + 读状态 + 确认动作接口

### 2.1 Jetson 环境

```bash
# JetPack 5 → Python 3.8；JetPack 6 → Python 3.10，先确认
python3 --version
python3 -m venv ~/g1env && source ~/g1env/bin/activate
```

安装官方 SDK（依赖和版本以 [unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python) 当前 README 为准）：

```bash
pip install unitree-sdk2py        # 或 git clone 后 pip install -e .
```

国内网络在 Jetson 上拉 GitHub 失败的备选：手机热点；Windows 下载后 `scp` 上去；
或走 ghproxy 镜像（阶段 1 实测 13MB/s 那个）。SDK 通常还要 CycloneDDS
（`pip install cyclonedds`）和把朝向机器人网口的 MTU 设为 1454（宇树文档要求）。

### 2.2 跑"读状态"示例（只读，绝对安全）

1. 找示例：`ls <sdk目录>/example/`，G1 相关的高层示例（读电量、位姿、运动模式）；
2. 跑通并记录输出——这一步证明 DDS 通信正常；
3. 读不到状态先别往下走：九成是网络/MTU/DDS 配置问题。

### 2.3 确认四个动作的 SDK 接口（本阶段最重要的产出）

不要猜接口，用这两招在 Jetson 上**自己查证**（以你装的 SDK 版本为准）：

```bash
# 招式一：看官方示例怎么调
ls example/g1/ && cat example/g1/high_level/*.py
# 招式二：直接问 Python
python -c "from unitree_sdk2py.g1.loco.loco_client import LocoClient; help(LocoClient)"
grep -ri "wave\|gesture\|arm" <sdk包目录> | head   # 找挥手类接口
```

可能的候选（**必须实测确认**，别当真）：高层运动客户端通常有站立/坐下/阻尼/
停止移动一类方法；"挥手"要找手臂或手势接口——**找不到就按 README 附录 D 降级，
第一版只做 stand / sit / stop**。

实测顺序（安全优先）：

1. `stand`（站立）→ 人退到 2 米外观察
2. `stop`（急停/阻尼）→ 确认随时能停
3. `sit`（坐下）
4. `wave`（挥手，如有接口）

每测一个：人在急停旁、地面空旷、电量 50%+。

### 2.4 产出：接口映射表（写进本文档）

| intent | SDK 调用（实测填入） | 备注 |
|---|---|---|
| stand | | |
| sit | | |
| wave | | 找不到接口则此行划掉 |
| stop | | 永远保留，可用阻尼/急停实现 |

## 3. 第 5 周：Jetson 上的"键盘控制版"安全服务

### 3.1 架构（和阶段 1 代码的对应关系）

```text
键盘输入 stand/sit/wave/stop
   ↓
SafetyLayer（robot/control_service.py，原样复用：白名单/冷却/stop 直通）
   ↓
G1Robot 适配器（新增：接口同 FakeRobot 的 perform(action)，内部调 2.4 的 SDK 调用）
   ↓
unitree_sdk2_python → G1
```

外层再加一个**看门狗**（新逻辑）：超过 N 秒（建议 10~15）没有收到任何指令/心跳
且机器人不在安全姿态 → 主动执行 stop，防止"程序僵死还以为自己在控制"。

### 3.2 开发方式（强烈推荐）

Skeleton 先在 Windows 写好 + 用 FakeRobot 全量测试（pytest），到 Jetson 只填
2.4 的接口映射。ZCode 可以提前生成这个骨架（G1Robot 真机方法留 TODO 桩），
现场工作量从"写服务"降到"填空 + 实测"。

### 3.3 验收四条怎么测

| 验收标准 | 测法 |
|---|---|
| 四个动作全部正确执行 | 键盘依次输入 stand/sit/wave（若有），人旁观确认 |
| 乱输入不触发任何动作 | 输入 `dance`、`sitdown!`、空行、乱码 → 应全部被拒并提示 |
| 动作执行中输入 stop 立即停 | wave/sit 过程中（动作没做完）敲 `stop` |
| 断网不持续发指令 | 杀掉输入源/拔网线后等 N 秒 → 看门狗自动进安全状态（日志可见） |

日志：沿用阶段 1 的 commands.log 格式，每条输入都留痕。

## 4. 安全清单（每次真机测试前过一遍）

- [ ] 电量 ≥ 50%
- [ ] 场地空旷，2 米内无人无易倒物
- [ ] 急停装置在手边且演练过
- [ ] 第一次执行新动作：人站在急停旁
- [ ] 动作顺序永远：stand → stop 先行验证，再测其他
- [ ] 任何异常 → 先 stop，再排查

## 5. 完成标志

阶段 2 结束时你应该拥有：Jetson 上一个常驻进程，键盘输入四个动作词驱动机器人，
乱输入被拒，stop 随时有效，看门狗兜底——**这就是未来语音系统的"手和脚"，
阶段 3 只需要把"嘴和耳朵"（Windows 语音）通过 JSON 接上它。**
