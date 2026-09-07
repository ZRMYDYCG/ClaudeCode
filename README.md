# Claude Code

macOS Python workspace（uv + CPython 3.14）。

## 环境要求

- `uv`（已安装到 `~/.local/bin`）
- Python `3.14`（由 uv 管理，勿用系统 `/usr/bin/python3`）

## 常用命令

```bash
# 同步依赖并创建 .venv
uv sync

# 运行
uv run python main.py
uv run claude-code

# 添加依赖
uv add requests
uv add --dev pytest

# 测试 / 检查
uv run pytest
uv run ruff check .
uv run mypy src
```

## 版本管理

```bash
uv python list          # 查看已安装 / 可下载版本
uv python install 3.13  # 安装其他版本
uv python pin 3.14      # 固定本项目版本（写入 .python-version）
```
