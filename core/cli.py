"""
终端主循环：读输入、分发斜杠命令、驱动 Agent。
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Literal

from pydantic_ai import Agent
from pydantic_graph import End

from core.agent import MODEL_NAME, agent, api_call_log
from core.session import append_messages, new_session_id
from core.ui.commands import COMMANDS, SessionState, print_part
from core.ui.input import Repl
from core.ui.render import console, print_welcome_banner

CommandAction = Literal["pass", "continue", "break"]


async def handle_command(user_input: str, state: SessionState) -> CommandAction:
    """
    处理以 / 开头的命令。
    返回 'pass'：不是命令，交给 Agent；
    返回 'continue'：命令已处理，进入下一轮；
    返回 'break'：命令要求退出程序。
    """
    if not user_input.startswith("/"):
        return "pass"
    cmd_name = user_input[1:].split()[0]
    command = COMMANDS.get(cmd_name)
    if command is None:
        console.print(f"未知命令：/{cmd_name}，输入 /help 查看可用命令\n")
        return "continue"
    result = command.handler(state)
    # 个别命令（如 /resume）要弹交互式列表，是异步的，需要 await
    if inspect.isawaitable(result):
        result = await result
    return "continue" if result else "break"


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


async def async_main() -> None:
    state = SessionState(
        model_name=MODEL_NAME,
        session_id=new_session_id(),
    )
    print_welcome_banner("Zrcoder")

    # 常驻输入区：输入框整个会话期间不消失
    repl = Repl(state)

    async def on_submit(user_input: str) -> None:
        # 每次回车提交一行输入，都走这里
        # 先处理 / 开头的命令
        action = await handle_command(user_input, state)
        if action == "break":
            # 命令要求退出，结束常驻输入区
            repl.exit()
            return
        if action == "continue":
            return

        # 核心 Agent 循环：开请求时显示 working...，结束 / 被打断后由 Repl 统一隐藏；
        # 中途按 ESC / Ctrl+C 会打断
        repl.start_working()
        await run_agent_loop(user_input, state)

    await repl.run(on_submit)


def main() -> None:
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, EOFError):
        pass


if __name__ == "__main__":
    main()
