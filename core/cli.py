"""
终端主循环：读输入、分发斜杠命令、驱动 Agent。
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from prompt_toolkit import PromptSession
from pydantic_ai import Agent
from pydantic_graph import End

from core.agent import MODEL_NAME, agent, api_call_log
from core.session import append_messages, new_session_id
from core.ui.commands import COMMANDS, SessionState, print_divider, print_part
from core.ui.render import console, print_welcome_banner

# PromptSession 比内置 input() 好用：支持左右移光标编辑，并记住本次输入历史
prompt_session: PromptSession[str] = PromptSession()

CommandAction = Literal["pass", "continue", "break"]


def read_user_input() -> str | None:
    """
    打印上横线并读一行用户输入；回车后再补一条下横线。
    返回 None 表示用户希望退出（Ctrl-C / Ctrl-D）。
    """
    print_divider()
    try:
        user_input = prompt_session.prompt("❯ ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    print_divider()
    return user_input


def handle_command(user_input: str, state: SessionState) -> CommandAction:
    """
    处理以 / 开头的命令。
    返回 'pass'：不是命令，主循环继续往下走交给 Agent；
    返回 'continue'：命令已处理，主循环跳到下一轮；
    返回 'break'：命令要求退出主循环。
    """
    if not user_input.startswith("/"):
        return "pass"
    cmd_name = user_input[1:].split()[0]
    command = COMMANDS.get(cmd_name)
    if command is None:
        console.print(f"未知命令：/{cmd_name}，输入 /help 查看可用命令\n")
        return "continue"
    return "continue" if command.handler(state) else "break"


def apply_result(state: SessionState, result: Any) -> None:
    """
    跑完一轮 Agent 后，把结果同步到 SessionState，并追加写入会话文件。
    """
    state.history = result.all_messages()
    usage = result.usage
    state.input_tokens += usage.input_tokens
    state.output_tokens += usage.output_tokens
    state.last_api_calls = list(api_call_log)
    append_messages(state.session_id, result.new_messages())


async def run_agent_loop(user_input: str, state: SessionState) -> None:
    """
    展开 agent.run_sync()，逐节点驱动 Agent 循环，每步实时打印。
    """
    api_call_log.clear()

    async with agent.iter(user_input, message_history=state.history) as run:
        node = run.next_node

        while not isinstance(node, End):
            node = await run.next(node)

            if Agent.is_call_tools_node(node):
                for response_part in node.model_response.parts:
                    print_part(response_part)

            elif Agent.is_model_request_node(node):
                for request_part in node.request.parts:
                    kind = getattr(request_part, "part_kind", None)
                    if kind in ("tool-return", "retry-prompt"):
                        print_part(request_part)

        apply_result(state, run.result)
    console.print()


def main() -> None:
    state = SessionState(
        model_name=MODEL_NAME,
        session_id=new_session_id(),
    )
    print_welcome_banner("Zrcoder")

    while True:
        # 读用户输入
        user_input = read_user_input()
        if user_input is None:
            break
        if not user_input:
            continue

        # 处理 / 开头的命令
        action = handle_command(user_input, state)
        if action == "break":
            break
        if action == "continue":
            continue

        # 核心 Agent 循环：自己驱动节点流转，实时打印每一步
        try:
            asyncio.run(run_agent_loop(user_input, state))
        except KeyboardInterrupt:
            console.print("\n[bold yellow]已中断[/]\n")
        except Exception as e:
            console.print(f"\n[bold red]✗ {type(e).__name__}: {e}[/]\n")


if __name__ == "__main__":
    main()
