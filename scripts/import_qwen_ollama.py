"""把 ModelScope 的 Qwen2.5-3B-Instruct GGUF 导入 Ollama（离线模型安装）。

用途：registry.ollama.org 不可达时（国内网络常见），用 ModelScope 的
官方 GGUF 代替 `ollama pull qwen2.5:3b`。导入后的模型名仍叫
qwen2.5:3b，程序配置无需改动。

用法：
  python scripts/import_qwen_ollama.py --download   # 下载 GGUF（约 2.1GB）并导入
  python scripts/import_qwen_ollama.py              # GGUF 已在本地时仅导入
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
GGUF_DIR = ROOT / "models" / "qwen2.5-3b-gguf"
GGUF_NAME = "qwen2.5-3b-instruct-q4_k_m.gguf"
MODEL_TAG = "qwen2.5:3b"
MODELSCOPE_REPO = "Qwen/Qwen2.5-3B-Instruct-GGUF"

# 标准 ChatML 模板（与 ollama 官方 qwen2.5 一致）
TEMPLATE = '''TEMPLATE """{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{ end }}{{ if .Prompt }}<|im_start|>user
{{ .Prompt }}<|im_end|>
{{ end }}<|im_start|>assistant
{{ .Response }}<|im_end|>
"""
PARAMETER stop "<|im_start|>"
PARAMETER stop "<|im_end|>"
'''


def ollama_exe() -> str:
    found = shutil.which("ollama")
    if found:
        return found
    default = Path.home() / "AppData/Local/Programs/Ollama/ollama.exe"
    if default.exists():
        return str(default)
    raise SystemExit("找不到 ollama.exe，请确认 Ollama 已安装")


def run_ollama(args: Sequence[str]) -> int:
    exe = ollama_exe()
    proc = subprocess.run(  # noqa: S603 - 参数为固定列表，无 shell
        [exe, *args], capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        print(out.strip())
    return proc.returncode


def download_gguf() -> None:
    print("从 ModelScope 下载 Qwen2.5-3B-Instruct GGUF（q4_k_m，约 2.1GB）……")
    from modelscope import snapshot_download

    snapshot_download(
        MODELSCOPE_REPO, local_dir=str(GGUF_DIR), allow_patterns=["*q4_k_m*"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true", help="GGUF 缺失时先从 ModelScope 下载")
    args = ap.parse_args()

    gguf = GGUF_DIR / GGUF_NAME
    if not gguf.exists():
        if not args.download:
            print(f"未找到 {gguf}；加 --download 先从 ModelScope 下载（约 2.1GB）")
            return 1
        download_gguf()
    print(f"GGUF 就绪：{gguf}（{gguf.stat().st_size / 1e9:.2f} GB）")

    modelfile = GGUF_DIR / "Modelfile"
    if not modelfile.exists():
        modelfile.write_text(f"FROM {GGUF_NAME}\n{TEMPLATE}", encoding="utf-8")

    print(f"导入 Ollama 为 {MODEL_TAG} ……")
    if run_ollama(["create", MODEL_TAG, "-f", str(modelfile)]) != 0:
        return 1

    print("当前模型列表：")
    return run_ollama(["list"])


if __name__ == "__main__":
    sys.exit(main())
