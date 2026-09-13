# 阶段 1 运行手册：Windows 语音对话原型

> 对应 README《五、阶段 1》。代码已全部完成，本文说明怎么跑起来、怎么逐条验收。

## 0. 环境（已配置好）

| 项目 | 状态 |
|---|---|
| Python | conda 环境 `unitree`（Python 3.11） |
| 显卡 | RTX 5060 8GB（Ollama 已确认跑在 GPU 上，占用约 2.8GB） |
| 麦克风/扬声器 | AULA-G7 耳机（默认设备） |
| 依赖 | 已装齐：funasr + torch(CPU) + kaldi-native-fbank + edge-tts 等 |
| Ollama | 0.34.0 已安装并常驻（127.0.0.1:11434） |
| 大模型 | qwen2.5:3b（q4_k_m，已导入，热身后单次解析 0.3~0.5 秒） |

所有命令都在仓库根目录 `C:\unitree_g1_voice` 下执行，Python 用：

```bash
# Git Bash / PowerShell 都可以
C:\Users\24331\miniconda3\envs\unitree\python.exe -m app.main
# 或者先 conda activate unitree，然后：
python -m app.main
```

## 1. 已完成的内容

第 2 周（录音 → 识别 → 回答 → 播报）：

- `audio/record.py`：`sounddevice` 录音，能量检测自动断句（说完停 1.2 秒自动结束、
  超过 10 秒截断、没人说话 2.5 秒返回空），支持 `--calibrate-mic` 校准
- `audio/asr.py`：FunASR + SenseVoice-Small 中文识别（首次运行自动下载模型）
- `audio/tts.py`：Edge-TTS 播报（联网）
- `llm/chat.py`：第 2 周对话原型（`--mode chat`）

第 3 周（唤醒词、意图解析与安全层）：

- 唤醒词“小宇”，兼容小雨/小语/小余（`app/textmatch.py`）
- 状态机 IDLE / LISTENING / PROCESSING（`app/state.py`）
- Qwen 意图解析只输出固定 JSON，pydantic 校验，intent 只有
  `stand / sit / wave / stop / none`（`llm/intent_parser.py`、`app/schemas.py`）
- 安全层：白名单、stop 直通最高优先级、动作冷却 ≥3 秒、执行前语音确认
  （`robot/control_service.py`）
- FakeRobot 模拟机器人（`robot/fake_robot.py`）
- 62 个 pytest 单测全部通过：`python -m pytest -q`

## 2. 验收清单（对应 README 第 2、3 周验收标准）

### 2.1 单元测试（已完成 ✅）

```bash
python -m pytest -q
```

覆盖：唤醒词同音字、“停止”不经过大模型、“跳起来”→none、乱文本/非法 JSON
不执行动作不崩溃、冷却时间、白名单拒绝、状态机转移。

### 2.2 冒烟测试（不需要麦克风）

```bash
python scripts/smoke_test.py             # TTS 合成"小宇，请挥手" → 播放 → 识别 → Ollama 解析
python scripts/smoke_test.py --skip-llm  # 没装好 Ollama 时先跑这个
```

预期输出：识别结果包含“挥手”，Ollama 解析 `intent=wave`。

### 2.3 第 2 周验收：连续 20 轮对话（需要你本人做）

```bash
python -m app.main --mode chat
```

对麦克风正常说 20 轮话（闲聊即可），观察：识别文字 → 模型回答 → 语音播报，
全程程序不退出。

### 2.4 第 3 周验收（需要你本人做）

```bash
python -m app.main          # assistant 模式
```

逐条验证：

| 你说 | 预期 |
|---|---|
| 小宇，请挥手 | 问“即将执行挥手，确认吗？” → 答“好的” → 执行 + 播报 |
| 停止 | 不问确认、不经过大模型，立即 stop |
| 小宇，跳起来 | 回复“我暂时不会……”，不执行 |
| 小宇，你好 | 闲聊回答，不执行动作 |
| （挥手确认后 3 秒内）小宇，坐下 | “动作太频繁”被冷却拦下 |
| 乱说话/沉默 | 忽略或超时回待命，程序不崩 |

日志：`logs/commands.log`（时间 | 原文 | intent | 结果）、`logs/assistant.log`。

## 3. 常用命令

```bash
python -m app.main --rules          # 不用 Ollama，关键词解析（先跑通流程用）
python -m app.main --no-confirm     # 跳过执行前确认（熟练后/演示开关）
python -m app.main --once           # 只听一句话（调试）
python -m app.main --calibrate-mic  # 测环境噪音，得到 energy_threshold 建议值
python -m app.main --list-devices   # 查看麦克风/扬声器列表
```

## 4. 常见问题

| 现象 | 处理 |
|---|---|
| 说了话没反应 | 阈值偏高：`python -m app.main --calibrate-mic`，按建议调 `config/settings.yaml` 的 `audio.energy_threshold`（调小） |
| 没说话也触发 | 环境吵：同上，把阈值调大 |
| 用错麦克风 | `--list-devices` 找到编号，填到 `audio.input_device` |
| TTS 没声音/报错 | edge-tts 需要联网；确认默认输出设备；实在不行 `tts.engine: console` 只看文字 |
| Ollama 报不可用 | `ollama serve` 或打开 Ollama 程序；`ollama list` 确认有 qwen2.5:3b（没有就跑 `python scripts/import_qwen_ollama.py --download`）；程序会自动退回规则解析，不会崩 |
| Ollama 首次回答很慢/超时 | 冷启动载入显存属正常（已把超时调到 60 秒）；之后每次 <1 秒 |
| 首次启动很久 | SenseVoice 模型首次下载（几百 MB），之后走缓存 |
| 命令行中文乱码 | PowerShell 里执行 `chcp 65001` 或设置环境变量 `PYTHONUTF8=1` |
| 自己的播报被录进去 | 戴耳机，或调大 `tts.speak_pause`（默认 0.2 秒） |

## 5. Ollama 模型安装（国内网络备选方案，已执行）

你的网络连不上 `registry.ollama.org`，`ollama pull` 用不了。已改用 ModelScope 的
官方 GGUF 导入，模型名仍是 `qwen2.5:3b`，配置不用改：

```bash
python scripts/import_qwen_ollama.py --download   # 下载 GGUF（约 2.1GB）并导入
python scripts/import_qwen_ollama.py              # 本地已有 GGUF 时仅重新导入
```

将来重装系统或迁移 Jetson 时重复执行即可。Ollama 安装包直连慢时，可用
`https://ghproxy.net/https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe`
（实测 13MB/s）。

注意：**Ollama 重启后的第一次调用要重新把模型载入显存，可能超过 20 秒**，
所以配置里 `llm.ollama.timeout` 已设为 60 秒；热身后单次解析 0.3~0.5 秒。
程序对超时的兜底是自动退回关键词规则解析（`--rules` 同款），不会崩。

## 6. 下一步（阶段 2 提示）

- 安全层 `robot/control_service.py` 已按“未来包上网络 + SDK”的形态写好，
  阶段 2 在 Jetson 上加 `unitree_sdk2_python` 绑定即可；
- `robot/jetson_client.py` 留了阶段 3 的 JSON 协议桩；
- 显存 8GB：qwen2.5:3b 稳定，想试 7B 改 `llm.ollama.model: qwen2.5:7b`。
