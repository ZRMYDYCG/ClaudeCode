#!/usr/bin/env bash
# 规范发版：更新 CHANGELOG + version → commit → tag → push → GitHub Release
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" || ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9.]+)?$ ]]; then
  echo "用法: $0 <X.Y.Z>" >&2
  echo "示例: $0 0.2.0" >&2
  exit 1
fi

TAG="v${VERSION}"
DATE="$(date -u +%Y-%m-%d)"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "工作区不干净，请先提交或暂存后再发版。" >&2
  git status --short >&2
  exit 1
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" && "$branch" != "master" ]]; then
  echo "请在 main/master 上发版（当前: ${branch}）。" >&2
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag ${TAG} 已存在。" >&2
  exit 1
fi

if ! grep -q '^## \[Unreleased\]' CHANGELOG.md; then
  echo "CHANGELOG.md 缺少 ## [Unreleased] 段。" >&2
  exit 1
fi

# Unreleased 下至少要有一条非空 bullet（跳过空的 ### 标题）
unreleased_body="$(
  awk '
    /^## \[Unreleased\]/ {grab=1; next}
    /^## \[/ && grab {exit}
    grab {print}
  ' CHANGELOG.md
)"
if ! printf '%s\n' "$unreleased_body" | grep -qE '^[[:space:]]*-[[:space:]]+[^[:space:]]'; then
  echo "CHANGELOG.md 的 [Unreleased] 没有条目。请先记录本次用户可见变化。" >&2
  exit 1
fi

current_version="$(
  python3 - <<'PY'
import tomllib
from pathlib import Path
print(tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
PY
)"
if [[ "$current_version" == "$VERSION" ]]; then
  echo "pyproject.toml 已是 ${VERSION}，请确认是否重复发版。" >&2
  exit 1
fi

python3 - "$VERSION" "$DATE" <<'PY'
import re
import sys
from pathlib import Path

version, date = sys.argv[1], sys.argv[2]
path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")

# 取出 Unreleased 正文（不含标题行）
m = re.search(
    r"## \[Unreleased\]\n(?P<body>.*?)(?=\n## \[)",
    text,
    flags=re.S,
)
if not m:
    sys.exit("无法解析 Unreleased 段")
body = m.group("body").rstrip() + "\n"

empty_sections = (
    "### Added\n\n### Changed\n\n### Fixed\n\n### Removed\n\n"
)
# 去掉空的分类标题，只保留有 bullet 的小节
kept: list[str] = []
section: list[str] = []
for line in body.splitlines(keepends=True):
    if line.startswith("### "):
        if section and any(l.startswith("- ") or l.startswith("-") for l in section[1:]):
            # 段内有内容
            if any(re.match(r"- .+", l) for l in section[1:]):
                kept.extend(section)
        section = [line]
    else:
        section.append(line)
if section and any(re.match(r"- .+", l) for l in section[1:]):
    kept.extend(section)
release_body = "".join(kept).rstrip() + "\n"
if not re.search(r"^- .+", release_body, flags=re.M):
    # fallback：保留原始 body（已在 bash 校验过有 bullet）
    release_body = body

new_unreleased = (
    "## [Unreleased]\n\n"
    "### Added\n\n"
    "### Changed\n\n"
    "### Fixed\n\n"
    "### Removed\n\n"
)
release_header = f"## [{version}] - {date}\n\n"
replacement = new_unreleased + release_header + release_body + "\n"

text2, n = re.subn(
    r"## \[Unreleased\]\n.*?(?=\n## \[)",
    replacement,
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    sys.exit("替换 Unreleased 失败")

# 更新底部链接
# [Unreleased]: ...compare/vOLD...HEAD  → compare/vNEW...HEAD
text2, n = re.subn(
    r"\[Unreleased\]:\s*https://github\.com/ZRMYDYCG/ClaudeCode/compare/v[^.]+\.[^.]+\.[^/]+(\S*)\.\.\.HEAD",
    f"[Unreleased]: https://github.com/ZRMYDYCG/ClaudeCode/compare/v{version}...HEAD",
    text2,
    count=1,
)
if n != 1:
    # 宽松匹配
    text2, n = re.subn(
        r"\[Unreleased\]:\s*\S+",
        f"[Unreleased]: https://github.com/ZRMYDYCG/ClaudeCode/compare/v{version}...HEAD",
        text2,
        count=1,
    )
    if n != 1:
        sys.exit("更新 [Unreleased] 链接失败")

# 在 [Unreleased] 链接后插入本版本链接（若尚无）
version_link = (
    f"[{version}]: https://github.com/ZRMYDYCG/ClaudeCode/releases/tag/v{version}"
)
if f"[{version}]:" not in text2:
    text2 = re.sub(
        r"(\[Unreleased\]:\s*\S+\n)",
        r"\1" + version_link + "\n",
        text2,
        count=1,
    )

path.write_text(text2, encoding="utf-8")
print(f"CHANGELOG.md → [{version}] - {date}")
PY

python3 - "$VERSION" <<'PY'
import re
import sys
from pathlib import Path

version = sys.argv[1]
path = Path("pyproject.toml")
text = path.read_text(encoding="utf-8")
text2, n = re.subn(
    r'(?m)^(version\s*=\s*")([^"]+)(")',
    rf"\g<1>{version}\g<3>",
    text,
    count=1,
)
if n != 1:
    sys.exit("无法更新 pyproject.toml version")
path.write_text(text2, encoding="utf-8")
print(f"pyproject.toml version → {version}")
PY

# 从 CHANGELOG 抽出本版本说明，供 GitHub Release
notes="$(
  python3 - "$VERSION" <<'PY'
import re
import sys
from pathlib import Path

version = sys.argv[1]
text = Path("CHANGELOG.md").read_text(encoding="utf-8")
m = re.search(
    rf"## \[{re.escape(version)}\][^\n]*\n(?P<body>.*?)(?=\n## \[|\Z)",
    text,
    flags=re.S,
)
if not m:
    sys.exit(f"找不到版本段 {version}")
body = m.group("body").strip()
# 去掉文件末尾的链接定义（若被吃进 body）
body = re.split(r"\n\[", body, maxsplit=1)[0].rstrip()
print(body)
PY
)"

git add CHANGELOG.md pyproject.toml
git commit -m "chore(release): v${VERSION}"

git tag -a "$TAG" -m "Release ${TAG}"
git push origin HEAD
git push origin "$TAG"

gh release create "$TAG" \
  --title "$TAG" \
  --notes "$(printf '%s\n\n%s\n' "## What's Changed" "$notes")"$'\n\n'"**PyPI:** https://pypi.org/project/zrcoder/${VERSION}/"

echo
echo "已创建 ${TAG}。等待 Actions「Publish」把包推到 PyPI。"
echo "查看: https://github.com/ZRMYDYCG/ClaudeCode/actions"
