# Releasing

发版遵循 [SemVer](https://semver.org/) + [Keep a Changelog](https://keepachangelog.com/)。

版本号**唯一来源**是 `pyproject.toml` 的 `project.version`。Git tag 必须是 `vX.Y.Z`，且与该字段一致。

## 日常开发

1. 用 [Conventional Commits](https://www.conventionalcommits.org/) 写提交（`feat` / `fix` / `docs` / `ci` …）。
2. 合并进 `main` 后，把用户可见变化记到 `CHANGELOG.md` 的 **`[Unreleased]`** 对应小节：
   - `Added` / `Changed` / `Fixed` / `Removed`
3. 不要在日常提交里改版本号。

## 发一个正式版

在干净的 `main` 上执行（把 `0.2.0` 换成目标版本）：

```bash
./scripts/release.sh 0.2.0
```

脚本会：

1. 检查工作区干净、当前在 `main`
2. 确认 `CHANGELOG.md` 的 `[Unreleased]` 有实质内容
3. 把 Unreleased 收成 `[0.2.0] - YYYY-MM-DD`，并更新底部对比链接
4. 写入 `pyproject.toml` 的 `version`
5. 提交 `chore(release): v0.2.0`
6. 打 tag `v0.2.0` 并 `git push`（含 tag）
7. 用该版本的 changelog 段落创建 GitHub Release

创建 Release 会触发 [`.github/workflows/publish.yml`](.github/workflows/publish.yml)：跑检查 → `uv build` → 发布到 PyPI。

### 手动等价步骤

若不用脚本，按同一顺序操作即可：改 changelog → 改 version → commit → `git tag vX.Y.Z` → push → `gh release create`。

## PyPI 鉴权（二选一）

### A. Trusted Publishing（推荐）

1. PyPI → 项目 `zrcoder` → Publishing → Add a new pending/trusted publisher  
2. 填：Owner `ZRMYDYCG`，Repository `ClaudeCode`，Workflow `publish.yml`，Environment `pypi`  
3. GitHub → Settings → Environments → 新建 `pypi`（可加保护规则）

### B. API token

在仓库 Secrets 增加 `UV_PUBLISH_TOKEN`（或 `PYPI_TOKEN`）。Workflow 会优先用 Trusted Publishing，失败时可改用 token。

## 版本号怎么选

| 变更 | 版本 |
|------|------|
| 修 bug、小改动，兼容 | `PATCH`（0.1.0 → 0.1.1） |
| 新功能，兼容 | `MINOR`（0.1.0 → 0.2.0） |
| 破坏性变更 | `MAJOR`（0.1.0 → 1.0.0） |

预发布可用 `0.2.0rc1`（tag `v0.2.0rc1`），仅在需要时使用。

## 检查清单

- [ ] CI 在 `main` 上是绿的
- [ ] `CHANGELOG.md` Unreleased 已写清用户可见变化
- [ ] `./scripts/release.sh X.Y.Z` 成功
- [ ] GitHub Release 页面笔记正确
- [ ] https://pypi.org/project/zrcoder/ 出现新版本
- [ ] `uv tool install zrcoder==X.Y.Z` 可安装并启动
