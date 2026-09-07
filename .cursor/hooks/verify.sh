#!/usr/bin/env bash
# Agent 一轮结束后跑类型检查 + 测试（stop）。
# 失败时返回 followup_message，让 Agent 继续修；成功或跳过则输出 {}。
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || {
  echo '{}'
  exit 0
}

input="$(cat)"
status="$(printf '%s' "$input" | jq -r '.status // empty')"
loop_count="$(printf '%s' "$input" | jq -r '.loop_count // 0')"

# 只在正常完成时校验；用户中止 / error 不打扰
if [[ "$status" != "completed" ]]; then
  echo '{}'
  exit 0
fi

if ! [[ "$loop_count" =~ ^[0-9]+$ ]]; then
  loop_count=0
fi

if [[ -x "$ROOT/.venv/bin/mypy" && -x "$ROOT/.venv/bin/pytest" ]]; then
  MYPY=("$ROOT/.venv/bin/mypy")
  PYTEST=("$ROOT/.venv/bin/pytest")
elif command -v uv >/dev/null 2>&1; then
  MYPY=(uv run mypy)
  PYTEST=(uv run pytest)
else
  echo '{}'
  exit 0
fi

export API_KEY="${API_KEY:-test-api-key}"
export BASE_URL="${BASE_URL:-https://example.com/v1}"
export MODEL_NAME="${MODEL_NAME:-test-model}"

failures=""

mypy_out="$("${MYPY[@]}" core 2>&1)" && mypy_code=0 || mypy_code=$?
if [[ "$mypy_code" -ne 0 ]]; then
  failures+="### mypy (exit ${mypy_code})"$'\n'"${mypy_out}"$'\n\n'
fi

pytest_out="$("${PYTEST[@]}" 2>&1)" && pytest_code=0 || pytest_code=$?
if [[ "$pytest_code" -ne 0 ]]; then
  failures+="### pytest (exit ${pytest_code})"$'\n'"${pytest_out}"$'\n\n'
fi

if [[ -z "$failures" ]]; then
  echo '{}'
  exit 0
fi

max_chars=3500
if [[ ${#failures} -gt $max_chars ]]; then
  failures="${failures:0:max_chars}"$'\n…(truncated)…'
fi

msg="$(
  cat <<EOF
类型检查或测试未通过（stop hook，loop_count=${loop_count}）。请根据下面输出修复，修完后不要只解释——直接改代码直到检查通过。

${failures}
EOF
)"

jq -n --arg msg "$msg" '{followup_message: $msg}'
exit 0
