# 宇树 G1 EDU 语音控制开发计划（机载 Jetson 独立运行版）

> **最终目标**：不连接任何电脑，直接对 G1 EDU 说话——"小宇，挥手"，它回答"好的，我来挥手"并执行动作；喊"停止"立即停下。
>
> **技术路线**：Windows 上开发原型 → 局域网联调 → 大脑迁移到机载 Jetson → 完全独立运行。
>
> **时间估算**：约 12 周（按每周投入 5～10 小时估算，可伸缩）。每个阶段都有验收标准，**通过验收再进入下一阶段**。

---

## 一、总体架构

**开发期（阶段 1～3）：大脑在 Windows，执行在 Jetson**

```text
Windows 电脑                           G1 EDU 机载 Jetson
┌────────────────────────┐             ┌────────────────────────┐
│ 电脑麦克风               │             │ 安全控制层（常驻）        │
│   ↓                    │             │   ├─ 动作白名单          │
│ 语音识别 SenseVoice     │   局域网     │   ├─ stop 直通          │
│   ↓                    │ ─────────→  │   ├─ 超时/断网保护       │
│ Qwen 意图理解           │  固定 JSON   │   └─ 日志               │
│   ↓                    │             │   ↓                    │
│ 语音合成                │             │ Unitree SDK（DDS）      │
└────────────────────────┘             └───────────┬────────────┘
                                                   ↓
                                                G1 执行动作
```

**最终形态（阶段 4～6）：全部在 Jetson 上，不再需要 Windows**

```text
G1 麦克风 → 唤醒词"小宇" → SenseVoice 识别 → Qwen 意图 → 安全层 → SDK → G1 动作
                                                    → Piper 合成 → G1 扬声器播报
```

三条设计原则（贯穿全程）：

1. **安全控制层从第一天起就放在 Jetson 上**，之后只迁移"大脑"，安全层永远不动；
2. **大模型只输出固定 JSON 意图**（`stand / sit / wave / stop / none`），永远不直接控制关节；
3. **"停止"不经过大模型**，优先级最高。

---

## 二、硬件与软件清单

| 项目 | 内容 | 状态 |
|---|---|---|
| 机器人 | Unitree G1 EDU（含机载 Jetson） | 已有 |
| 开发机 | Windows + NVIDIA 显卡 | 已有（型号待确认） |
| 机载计算 | Jetson Orin NX（**型号 / 内存待确认，见阶段 0**） | 待确认 |
| 网络 | 电脑与 G1 同一局域网；G1 内网通常在 192.168.123.x 网段（以宇树文档为准） | 待确认 |
| 安全 | 急停装置、空旷场地 | 必备 |
| 建议购买 | 一个几十元的 USB 麦克风 + 小音箱（接 Jetson，过渡期测试用） | 可选 |

> 虚拟机不需要参与这个项目：没有显卡跑不了模型，只用来偶尔编辑文件即可。

软件栈（一套代码，两个运行位置，用配置切换）：

| 功能 | Windows 开发期 | Jetson 最终版 |
|---|---|---|
| 语音识别 | FunASR + SenseVoice-Small | 同左 |
| 意图理解 | Ollama + Qwen2.5-7B（显存够）/ 3B | Ollama + Qwen2.5-3B 4-bit |
| 语音合成 | Edge-TTS（最简单，需联网） | Piper（完全离线，约 100MB） |
| 唤醒词 | 识别文本中判断"小宇" | 同左（后续可换 sherpa-onnx 关键词检测） |
| 机器人控制 | —— | unitree_sdk2_python |
| 编辑器 | VS Code | VS Code Remote-SSH 直连 Jetson |

---

## 三、模型选型（按 Jetson 内存）

> Jetson 的内存是 CPU/GPU 共享的（统一内存），系统和桌面环境也要占内存，所以预算要留余量。

| 功能 | 最低配（8GB 也能跑） | 推荐配（16GB） | 说明 |
|---|---|---|---|
| 语音识别 | SenseVoice-Small（FunASR） | 同左 | 中文效果好、速度快，模型几百 MB |
| 唤醒词 | ASR 文本判断"小宇" | 同左 | 第一版够用，无需额外模型 |
| 意图理解 | Qwen2.5-3B-Instruct 4-bit（约 2GB） | 可尝试 Qwen2.5-7B 4-bit（约 4.5GB） | Ollama 运行，默认就是 4-bit 量化 |
| 语音合成 | Piper 中文音色 | 同左 | 完全离线；CosyVoice 对 Jetson 偏重，不推荐 |
| 机器人控制 | unitree_sdk2_python | 同左 | 只调用白名单动作 |

---

## 四、阶段 0：确认硬件与安全准备（第 1 周）

**目标**：把所有未知信息搞清楚，避免后面返工。

### 1. 确认 Jetson（SSH 登录机载电脑，IP 和账号以宇树文档为准）

依次执行并记录结果：

```bash
cat /proc/device-tree/model   # Jetson 型号，如 NVIDIA Orin NX 16GB
free -h                       # 内存
df -h                         # 磁盘剩余空间
cat /etc/nv_tegra_release     # JetPack / L4T 版本
nvpmodel -q                   # 当前功耗模式
```

> JetPack 版本决定系统 Python：JetPack 5 → Python 3.8（Ubuntu 20.04）；JetPack 6 → Python 3.10（Ubuntu 22.04）。后面建虚拟环境时注意对应。

### 2. 确认 Windows 侧

- 显卡型号与显存：任务管理器 → 性能 → GPU，或命令 `nvidia-smi`；
- 安装 Python 3.10 / 3.11、Git、VS Code。

### 3. 安全准备

- 确认急停按钮 / 遥控器急停可用，**实际演练一次**；
- 测试场地空旷，周围 2 米内无人、无易倒物品；
- 调试时 G1 电量保持 50% 以上；
- 确认宇树文档允许在机载 Jetson 上安装自定义软件。

### 验收：填完这张表

| 待确认项 | 结果 |
|---|---|
| Jetson 型号 / 内存 | |
| JetPack 版本 / 系统 Python | |
| Jetson 磁盘剩余 / IP / SSH 账号 | |
| Windows 显卡型号 / 显存 | |
| Unitree SDK 版本 | |
| 官方内置动作列表（哪些可调用、用什么接口） | |
| 急停方式（按钮 / 遥控器） | |

---

## 五、阶段 1：Windows 语音对话原型（第 2～3 周）

**不碰机器人**，先把"听得懂、说得出"的闭环做出来。

### 第 2 周：录音 → 识别 → 回答 → 播报

1. 搭项目骨架和虚拟环境（目录见附录 A）；
2. `sounddevice` 录音 3 秒存 wav、播放 wav；
3. FunASR（SenseVoice-Small）识别中文；
4. 安装 Ollama，`ollama run qwen2.5:3b`（显存 8GB 以上可试 7B）；
5. Edge-TTS 播报模型回复。

**验收**：连续 20 轮"说话 → 显示识别文字 → 模型回答 → 语音播报"，全程程序不退出；安静环境下"站起来 / 挥手 / 坐下 / 停止"识别基本准确。

### 第 3 周：唤醒词、意图解析与安全层（离线测试）

- **唤醒词"小宇"**：只有识别文本以"小宇"开头才处理；兼容常见同音字（小雨 / 小语 / 小余）；
- **状态机**：`IDLE / LISTENING / PROCESSING`，2～3 秒无后续语音自动回到 IDLE，录音过长自动截断；
- **意图解析**：Qwen 只输出固定 JSON（Prompt 见附录 B），intent 只能是 `stand / sit / wave / stop / none`；
- **安全层**：白名单校验、stop 最高优先级、动作间冷却时间（≥3 秒）、执行前语音确认（"即将执行挥手，确认吗？"）；
- 用 **FakeRobot**（模拟机器人类）代替真机跑通全部逻辑，并用 pytest 写单元测试。

**验收**：

- "小宇，请挥手" → `intent=wave` 并请求确认；
- "停止"不经过大模型，直接返回 stop；
- "跳起来" → `none`；闲聊 → `none`；
- 模型返回乱文本 / 非法 JSON 时不执行任何动作，程序不崩溃。

---

## 六、阶段 2：Jetson 就绪 + G1 键盘控制（第 4～5 周）

### 第 4 周：Jetson 环境 + SDK 通信测试

1. Jetson 上建 Python 虚拟环境，安装 [unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python)（官方仓库 example 目录下有 G1 相关示例，以仓库当前内容为准）；
2. 运行"读取状态"类示例：确认能读到 G1 状态、电量、当前运动模式；
3. **确认官方内置动作**：站立、坐下、挥手、停止分别用什么接口调用（以你拿到的 SDK 版本和文档为准），逐个手动验证并记录。

> 安全提示：第一次调用动作时，人在旁边随时按急停；地面空旷；先测 `stand` 和 `stop`，都正常后再测其他动作。

### 第 5 周：Jetson 上的"键盘控制版"（未来常驻的安全层）

在 Jetson 上写一个控制服务，行为如下：

```text
输入 stand / sit / wave / stop
  → 白名单校验 → 调用 SDK → 返回执行结果

规则：
  - 未知指令一律拒绝
  - stop 永远有效，可打断当前动作
  - 连续动作间隔 ≥ 3 秒
  - 一定时间无心跳/指令 → 自动进入安全状态
```

**验收**：

- 四个动作全部正确执行；
- 乱输入不会触发任何动作；
- 动作执行中输入 `stop` 能立即停下；
- 断开网络后程序不会持续发送控制指令（超时进入安全状态）。

---

## 七、阶段 3：PC 语音 → G1 动作联调（第 6 周）

把两台机器连起来。协议只传固定 JSON，**不传关节级指令**。

请求（Windows → Jetson）：

```json
{"action": "wave", "request_id": "20260912-001", "source": "voice"}
```

响应（Jetson → Windows）：

```json
{"ok": true, "action": "wave", "state": "executing"}
```

Windows 侧主流程（伪代码）：

```python
text = asr(record())
if not startswith_wake_word(text):      # "小宇"
    continue

intent = llm_parse(text)                 # 固定 JSON

if intent.action == "stop":
    send_to_jetson("stop")               # 直通，不确认
elif intent.action in ALLOWED_ACTIONS:
    if voice_confirm(intent):            # "即将执行挥手，确认吗？"
        send_to_jetson(intent.action)
        speak(intent.reply)
else:
    speak("我暂时不会执行这个指令")
```

**验收**：

- 电脑麦克风说"小宇，挥手" → 确认后 G1 执行；
- 动作执行中喊"停止"立即生效；
- 拔掉 Windows 与 Jetson 之间的网络 → Jetson 侧自动安全停止；
- 每条指令在两侧日志中都能查到。

> **到这里你就拥有了一个完整可用的语音控制机器人**——只是大脑还在 Windows 电脑上。接下来把它搬进机器人。

---

## 八、阶段 4：大脑迁移到 Jetson（第 7～9 周）

### 第 7 周：Jetson 基础环境

1. VS Code Remote-SSH 直连 Jetson 开发，Windows 只当编辑器和终端；
2. 安装：Python 虚拟环境、FunASR（SenseVoice）、Piper 中文语音、Ollama（Linux ARM64 版）；
3. 代码用 git 同步到 Jetson；
4. 配置切换：`audio.input: USB_MIC`（用建议购买的 USB 麦克风）、`tts.engine: piper`。

### 第 8 周：模型部署与性能调优

1. `ollama pull qwen2.5:3b`（4-bit 量化，约 2GB）；
2. 性能设置：`sudo nvpmodel -m 0`（最大功耗模式）、`sudo jetson_clocks`；
3. 安装 jetson-stats，用 `jtop` 实时观察内存/显存占用与温度；
4. 如果 Jetson 是 16GB 且温度可控，可尝试 Qwen2.5-7B 4-bit；否则留在 3B——**3B 对固定指令解析完全够用**。

**验收**：

- SenseVoice 识别 3 秒中文语音在 2 秒左右返回；
- Qwen 意图解析在 3 秒左右返回；
- 连续运行 30 分钟，jtop 显示内存有富余、温度不触发降频。

### 第 9 周：Jetson 本地全链路

USB 麦克风说话 → Jetson 上完整跑通：唤醒 → 识别 → Qwen → 安全层 → SDK → 动作 → Piper 播报。Windows 只开一个 SSH 终端看日志。

> 迁移后 `main.py` 与 `control_service.py` 在同一台 Jetson 上，JSON 协议不变，只是地址变成 localhost。

**验收**：

- 不依赖 Windows 上任何程序，G1 完成语音控制；
- 断开外网（只留机器人内部网络）一切正常。

---

## 九、阶段 5：接入 G1 麦克风与扬声器（第 10 周）

G1 头部的麦克风阵列会把音频以 RTP/UDP 多播形式发到机器人内部网络，机载 Jetson 可以直接接收；向 G1 扬声器播放声音也有对应的 UDP 接口。**具体端口、音频格式以 KuzmichAI 项目（附录 C）和宇树官方文档为准**——这一步最容易踩坑，所以放在大脑稳定之后。

保留三种音频模式，配置一键切换：

```yaml
audio:
  input: G1_MIC        # 可选 PC_MIC / USB_MIC / G1_MIC
  output: G1_SPEAKER   # 可选 PC_SPEAKER / USB_SPEAKER / G1_SPEAKER
```

注意：电机运行时识别率会下降，属正常现象。应对方法是在确认环节放宽匹配（"确认 / 是的 / 嗯 / 好"都算通过）。

**验收**：

- G1 麦克风在 2 米内稳定识别"小宇，挥手"；
- 电机运行时"停止"仍然可靠；
- G1 扬声器播报清晰；
- USB 麦克风模式保留可用（排错时用）。

---

## 十、阶段 6：脱机运行与稳定性测试（第 11～12 周）

### 测试清单

- 说错话 / 说半句话 / 环境嘈杂；
- 大模型超时或进程崩溃；
- 动作执行中喊"停止"；
- 连续快速重复同一指令；
- G1 电量低于 20% 时的行为（应拒绝动作并播报）；
- 长时间运行（≥2 小时）内存无泄漏；
- 断电重启后能否一键恢复服务。

### 工程化收尾

- 用 systemd 把主程序设为开机自启、崩溃自动重启；
- 日志轮转，只保留最近 N 天；
- 确认模式做成配置开关（演示时开确认，熟练后可关）。

### 最终验收

关掉 Windows、断开外网，只留 G1 本体，对它说：

```text
小宇，站起来   → G1 站立
小宇，挥手     → G1 挥手，并语音回复
小宇，坐下     → G1 坐下
停止！         → 任何时候立即停止
```

---

## 十一、安全规范（贯穿所有阶段）

1. `stop` 不经过大模型；任何异常优先进入安全状态；
2. 大模型只输出白名单意图，不输出关节角度、速度或代码；
3. `stand / sit / wave` 默认需要语音确认（可配置关闭）；
4. 动作执行中忽略重复指令，动作之间设冷却时间（≥3 秒）；
5. 每次动作前检查机器人状态与电量；
6. 调试期保持低速、短动作、有人看护、随时可按急停；
7. 网络断开、模型无响应、程序异常 → 超时进入安全状态并播报原因；
8. 所有指令写日志：时间、识别原文、intent、执行结果。

---

## 十二、第一版动作表

| 用户说法 | intent | 需确认 |
|---|---|---|
| 你好 / 在吗 | `none`（只回答） | — |
| 小宇，站起来 / 起立 | `stand` | 是 |
| 小宇，挥手 / 打个招呼 | `wave` | 是 |
| 小宇，坐下 / 坐好 | `sit` | 是 |
| 停止 / 别动 / 停下来 | `stop` | 否（直通） |
| 跳舞 / 跑步 / 翻跟头 | `none`（回复"我暂时不会"） | — |

---

## 附录 A：项目目录结构

```text
g1_voice_control/
├─ app/
│  ├─ main.py             # 主循环：唤醒 → 识别 → 意图 → 派发
│  ├─ config.py
│  └─ schemas.py          # intent JSON 校验（pydantic）
├─ audio/
│  ├─ record.py           # 录音（PC_MIC / USB_MIC / G1_MIC 三种后端）
│  ├─ asr.py              # FunASR / SenseVoice
│  └─ tts.py              # edge-tts / piper 双后端
├─ llm/
│  └─ intent_parser.py    # Ollama 调用 + Prompt
├─ robot/
│  ├─ fake_robot.py       # 无真机时的模拟机器人（测试用）
│  ├─ jetson_client.py    # Windows 侧：向 Jetson 发 JSON 指令
│  └─ control_service.py  # Jetson 侧：安全层 + SDK（常驻服务）
├─ config/
│  └─ settings.yaml
├─ tests/
└─ logs/
```

## 附录 B：意图解析 Prompt 与输出格式

系统提示词：

```text
你是机器人指令解析器。
只能从 stand、sit、wave、stop、none 中选择一个 intent。
不能输出关节角度、速度或控制代码。
无法确定时返回 none。
只输出 JSON。
```

输出格式：

```json
{
  "intent": "wave",
  "reply": "好的，我来挥手。",
  "confidence": 0.92
}
```

## 附录 C：参考项目

| 项目 | 用途 |
|---|---|
| [unitreerobotics/unitree_sdk2_python](https://github.com/unitreerobotics/unitree_sdk2_python) | G1 控制基础（必装） |
| [ArtZap/KuzmichAI-UnitreeG1](https://github.com/ArtZap/KuzmichAI-UnitreeG1) | G1 麦克风音频接收（RTP 多播）、整体架构参考 |
| [ting-zheng/unitree_g1_agent](https://github.com/ting-zheng/unitree_g1_agent) | ASR→LLM→TTS→G1 流程参考 |
| [star-nexus/G1-Robot-Agents-Speech](https://github.com/star-nexus/G1-Robot-Agents-Speech) | SenseVoice + Jetson 部署参考 |
| [modelscope/FunASR](https://github.com/modelscope/FunASR) | 中文语音识别 |
| [ollama/ollama](https://github.com/ollama/ollama) | 本地大模型运行（Windows / Jetson 通用） |
| [rhasspy/piper](https://github.com/rhasspy/piper) | 离线语音合成 |

## 附录 D：风险与备选方案

| 风险 | 备选方案 |
|---|---|
| Jetson 只有 8GB 内存 | 只用 Qwen 3B；再紧张就退回规则解析（关键词映射，不用大模型） |
| FunASR 在 Jetson 上安装困难 | 改用 sherpa-onnx（SenseVoice 的 ONNX 版，依赖更轻） |
| 官方 SDK 没有"挥手"接口 | 第一版只保留 stand / sit / stop，wave 向宇树确认接口后再加 |
| G1 麦克风多播收不到 / 音频格式搞不定 | 保留 USB 麦克风 + 小音箱方案，功能不受影响 |
| Ollama 在 Jetson 上 GPU 不工作 | 用 CPU 模式跑 3B（慢一些但可用），或手动编译 llama.cpp |
| Windows 显存不足 | 开发期就用 3B，或临时用 Qwen 云 API（仅开发期） |

## 现在就可以做的 4 件事

1. SSH 登录 Jetson，跑阶段 0 的 5 条命令，填完硬件确认表；
2. Windows 查显卡型号和显存；
3. 安装 Python 3.10 / 3.11 + VS Code + Git；
4. 建好项目仓库，先写 `fake_robot.py`，把阶段 1 的测试框架搭起来。
