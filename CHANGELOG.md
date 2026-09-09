# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Print `retry-prompt` parts during the live agent loop
- Catch Ctrl-C / unexpected errors in the agent turn without exiting the REPL
- Auto-retry model HTTP 5xx / API errors with exponential backoff
- Turn tool execution exceptions into tool results so the agent can recover
- Raise `ModelRetry` from tools for fixable errors (missing path, permission, directory)
- Persist each turn's new messages to `~/.zrcoder/projects/<cwd>/<session>.jsonl`
- `/resume` command to pick and replay a past session via questionary
- Coerce flaky OpenAI-compatible ChatCompletion fields; retry `UnexpectedModelBehavior`

### Changed

### Fixed

### Removed

## [0.2.0] - 2026-09-08

### Added

- Stream agent steps live via `agent.iter` node loop

### Fixed

- Correct CLI imports to `core.agent` / `core.ui` (broken `agent` / `ui` absolute imports)


## [0.1.0] - 2026-09-08

### Added

- Terminal coding agent CLI (`zrcoder`) with OpenAI-compatible model providers
- Built-in tools: read file, write file, run shell commands
- Slash commands: `/help`, `/status`, `/new`, `/api-detail`, `/exit`
- Session token usage tracking and per-turn API call detail view
- Unit tests, GitHub Actions CI (ruff / mypy / pytest)
- Cursor hooks for format-on-edit and verify-on-stop
- First PyPI release under the package name `zrcoder`

[Unreleased]: https://github.com/ZRMYDYCG/ClaudeCode/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ZRMYDYCG/ClaudeCode/releases/tag/v0.2.0
[0.1.0]: https://github.com/ZRMYDYCG/ClaudeCode/releases/tag/v0.1.0
