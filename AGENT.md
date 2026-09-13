# Zrcoder — Agent Notes

终端编程助手（PyPI: `zrcoder`）。连 OpenAI 兼容 API，提供读写文件、执行命令、斜杠命令与会话恢复。

## Stack

- **Python 3.12+**，包管理用 **uv**
- **Pydantic AI**（`Agent` / tools / `Hooks` / `agent.iter`）
- UI：`prompt-toolkit` + `rich` + `questionary`
- 质量：`ruff` / `pytest` / `mypy --strict`

## Layout

| Path | Role |
|------|------|
| `core/cli.py` | REPL 主循环、斜杠命令分发、驱动 `agent.iter` |
| `core/agent/core.py` | Agent / model / instructions 装配 |
| `core/agent/tools.py` | `read_file` / `write_file` / `run_command` |
| `core/agent/hooks.py` | API 元数据、重试、工具权限、工具错误兜底 |
| `core/permissions.py` | `default` / `acceptEdits` / `bypass` + 审批 UI |
| `core/session.py` | `~/.zrcoder/projects/<cwd>/` 下的 jsonl 会话 |
| `core/ui/` | 输入、渲染、斜杠命令 |
| `main.py` | 兼容入口：`uv run python main.py` |

入口脚本：`zrcoder = core.cli:main`。

## Conventions

- 改代码前先对齐现有模块边界；工具错误：可纠正的用 `ModelRetry`，不可纠正的返回错误字符串，意外异常交给 `on_tool_execute_error`。
- 权限：只读工具默放行；危险 `run_command` 经 `register_self_check` 强制 `ask`；拒绝时把原因回填给模型，不要静默绕过。
- 风格：`from __future__ import annotations`、双引号、行宽 100；中文注释可以，但 API / 公开标识符用英文。
- 提交：Conventional Commits；用户可见变更记到 `CHANGELOG.md` 的 `[Unreleased]`。发版见 `RELEASING.md`。

## Commands

```bash
uv sync --group dev
uv run zrcoder          # 或 uv run python main.py
uv run ruff format .
uv run ruff check --fix .
uv run pytest
uv run mypy core
```

环境变量见 `.env.example`：`API_KEY`、`BASE_URL`、可选 `MODEL_NAME`。

## Skills

项目 skills 在 `.agents/skills/`（`.claude/skills/` 为 symlink）。与本仓库最相关：

- **AI**：`building-pydantic-ai-agents`、`pydantic-ai-harness`、`pydantic`
- **Python**：`async-python-patterns`、`python-testing-patterns`、`python-code-style`、`uv-package-manager`

锁文件：`skills-lock.json`。

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
