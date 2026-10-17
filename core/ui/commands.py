from __future__ import annotations

import difflib
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import questionary
from prompt_toolkit.application import in_terminal
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import Heading, Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.rule import Rule

from core import permissions, session
from core.agent import ReadFileState

from .render import console, print_step


class LeftAlignedHeading(Heading):
    """
    rich 默认把 Markdown 标题渲染成居中对齐，宽终端里看着像错位，覆盖成左对齐。
    """

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        text = self.text
        text.justify = "left"
        yield text


# 全局替换 Markdown 的标题渲染元素
Markdown.elements["heading_open"] = LeftAlignedHeading


@dataclass
class SessionState:
    """
    跨命令共享的会话状态，主循环把它传给每个命令处理函数。
    """

    history: list[Any] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model_name: str = ""
    # 最近一轮 user input 触发的所有 model API 调用记录
    last_api_calls: list[Any] = field(default_factory=list)
    # 当前会话 id，对应 ~/.…/projects/<cwd>/<id>.jsonl
    session_id: str = ""
    # 本会话的 readFileState，注入给文件工具；切换会话时换上新实例
    read_file_state: ReadFileState = field(default_factory=ReadFileState)


@dataclass
class Command:
    name: str
    description: str
    # handler 返回 False 表示主循环应当退出；可同步也可异步（如 /resume）
    handler: Callable[[SessionState], bool | Awaitable[bool]]


def print_divider() -> None:
    """
    每轮交互之前打印一条分割线，区分输入区域。Rule 会自适应终端宽度。
    """
    console.print(Rule(style="grey50"))


def _truncate(text: Any, limit: int = 120) -> str:
    """
    截断并 escape，用于 tool 参数 / 返回值 / 用户输入这类可能过长的内容。
    """
    text = str(text).strip()
    text = text if len(text) <= limit else text[:limit] + "..."
    return escape(text)


def _full(text: Any) -> str:
    """
    完整显示，只做 escape 不截断，用于 thinking 和 assistant text 这种用户关心的内容。
    """
    return escape(str(text).strip())


def _format_part_line(part: Any) -> str | None:
    """
    把一条消息里的单个 part 格式化为带 Rich markup 的字符串。
    版式：图标 + role 标签独占一行，内容换行到下一行，不用「|」分隔。
    """
    # 内容行统一缩进 2 格，和图标（占 2 格：图标 + 空格）后的 role 名对齐
    kind = part.part_kind
    if kind == "user-prompt":
        return f"[cyan]❯ user[/]\n  {_truncate(part.content)}"
    if kind == "thinking":
        # thinking 整块 dim，弱化视觉权重；不截断，完整保留思考过程
        return f"[dim]✻ thinking[/]\n  [dim]{_full(part.content)}[/]"
    if kind == "text":
        content = (part.content or "").strip()
        if not content:
            return None
        # assistant 是用户最关心的最终回答，完整显示
        return f"[green]● assistant[/]\n  {_full(content)}"
    if kind == "tool-call":
        # 命令、路径动辄上百字符，参数放宽到 500 字符再截断
        args = _truncate(part.args, 500)
        return f"[yellow]⏺ tool_call[/]\n  [yellow dim]{part.tool_name}({args})[/]"
    if kind == "tool-return":
        content = _truncate(part.content)
        return f"[magenta]✔ tool_return[/]\n  [magenta dim]{part.tool_name} -> {content}[/]"
    if kind == "retry-prompt":
        # 工具抛 ModelRetry 后，SDK 生成 retry-prompt 把错误反馈给模型
        content = _truncate(part.content)
        return f"[yellow]✘ tool_retry[/]\n  [yellow dim]{part.tool_name} -> {content}[/]"
    return None


def print_assistant_markdown(content: str) -> None:
    """
    模型的回复天然是 Markdown 格式，整块渲染出来，而不是打印原始文本。
    """
    console.print("[green]● assistant[/]")
    # Markdown 是块级渲染对象，没法跟在行内前缀后面，所以另起一行渲染；左缩进 2 格和 role 名对齐
    console.print(Padding(Markdown(content), (0, 0, 0, 2)))


# read / write 内容预览最多显示的行数，超出的折叠成「… +N 行」
_PREVIEW_MAX_LINES = 8


def _preview_numbered(content: str) -> str | None:
    """
    把内容加绿色行号、截断成预览，用于 write_file 的写入内容展示。
    """
    lines = content.splitlines()
    if not lines:
        return None
    width = len(str(len(lines)))
    shown = lines[:_PREVIEW_MAX_LINES]
    out = [f"  [green]{i:>{width}}[/] {escape(ln)}" for i, ln in enumerate(shown, 1)]
    if len(lines) > _PREVIEW_MAX_LINES:
        out.append(f"  [dim]… +{len(lines) - _PREVIEW_MAX_LINES} 行[/]")
    return "\n".join(out)


def _preview_diff(old: str, new: str) -> str:
    """
    用 difflib 把 old -> new 渲染成红绿 diff：删除行红、新增行绿、不变行 dim。
    """
    out = []
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        tag, body = line[:2], escape(line[2:])
        if tag == "- ":
            out.append(f"  [red]- {body}[/]")
        elif tag == "+ ":
            out.append(f"  [green]+ {body}[/]")
        elif tag == "  ":
            out.append(f"  [dim]  {body}[/]")
        # "? " 是 difflib 的字符级提示行，跳过不显示
    return "\n".join(out)


def _print_file_op(part: Any) -> bool:
    """
    文件工具的富展示：edit 红绿 diff、write 带行号写入预览、read 带行号读取结果。
    返回 True 表示已处理。
    """
    # 这里按工具名特判，没像 permissions 那样建注册表：
    # 展示逻辑依赖 rich，若让工具层注册渲染器，agent 层就会反向依赖 UI 层，得不偿失
    kind = part.part_kind
    if kind == "tool-call" and part.tool_name in ("edit_file", "write_file"):
        args = part.args_as_dict()
        path = escape(str(args.get("path", "")))
        # edit / write 的标签行与「工具名(路径)」内容行格式一致，统一打印，只有下方的预览不同
        console.print("[yellow]⏺ tool_call[/]")
        console.print(Padding(f"[yellow dim]{part.tool_name}({path})[/]", (0, 0, 0, 2)))
        if part.tool_name == "edit_file":
            console.print(_preview_diff(args.get("old_string", ""), args.get("new_string", "")))
        else:
            block = _preview_numbered(args.get("content", ""))
            if block:
                console.print(block)
        return True
    if kind == "tool-return" and part.tool_name == "read_file":
        # read_file 的返回已经是带行号的内容，按行截断预览
        console.print("[magenta]✔ tool_return[/]")
        console.print(Padding("[magenta dim]read_file[/]", (0, 0, 0, 2)))
        lines = str(part.content).splitlines()
        for ln in lines[:_PREVIEW_MAX_LINES]:
            console.print(f"  [dim]{escape(ln)}[/]")
        if len(lines) > _PREVIEW_MAX_LINES:
            console.print(f"  [dim]… +{len(lines) - _PREVIEW_MAX_LINES} 行[/]")
        return True
    return False


def print_part(part: Any) -> None:
    """
    渲染单个消息 part：assistant 文本走 Markdown 块渲染，文件操作走富展示，其余 part 是单行文本。
    """
    if part.part_kind == "text":
        content = (part.content or "").strip()
        if content:
            print_assistant_markdown(content)
            # 每个 role block 末尾留一个空行，块与块之间不那么挤
            console.print()
        return
    # 文件工具（read / edit / write）走专门的富展示
    if _print_file_op(part):
        console.print()
        return
    line = _format_part_line(part)
    if line:
        label, _, body = line.partition("\n")
        # body 形如 "  [markup]…"：去掉字面前导 2 空格，交给 print_step 用 Padding 缩进
        print_step(label, body[2:])


def print_agent_steps(new_messages: Iterable[Any]) -> None:
    """
    主循环里调用：显示这一轮 Agent 新增的中间过程（thinking、文本、工具调用、工具返回）。
    """
    for msg in new_messages:
        for part in msg.parts:
            # 主循环里不重复显示用户刚刚输入的内容
            if part.part_kind == "user-prompt":
                continue
            print_part(part)


def cmd_exit(state: SessionState) -> bool:
    console.print("再见 👋")
    return False


def cmd_help(state: SessionState) -> bool:
    console.print("可用命令：")
    for cmd in COMMANDS.values():
        console.print(f"  /{cmd.name:<10} {cmd.description}")
    console.print()
    return True


def cmd_new(state: SessionState) -> bool:
    """
    开启新会话：清空历史、token 计数、API 调用记录，换一个新的会话 ID。
    """
    state.history.clear()
    state.input_tokens = 0
    state.output_tokens = 0
    state.last_api_calls.clear()
    state.session_id = session.new_session_id()
    # 权限白名单是会话级的，「本会话不再询问」不该带进新会话
    permissions.state.session_allowed.clear()
    # readFileState 也是会话级的，新会话从空白开始，旧会话读过的文件不带进来
    state.read_file_state = ReadFileState()
    console.print("已开启新会话\n")
    return True


def _summary_line(mtime: datetime, prompt: str) -> str:
    """
    拼一条会话列表的展示文本：修改时间 + 首条用户输入摘要。
    """
    prompt = " ".join(str(prompt).split())
    if len(prompt) > 50:
        prompt = prompt[:50] + "..."
    return f"{mtime:%m-%d %H:%M}  {prompt}"


async def cmd_resume(state: SessionState) -> bool:
    """
    列出当前项目的历史会话，选中后恢复对话历史。
    它跑在 REPL 的事件循环里，所以是异步的：in_terminal 把终端让给 questionary，结束后再恢复输入框。
    """
    sessions = session.list_sessions()
    if not sessions:
        console.print("(当前项目还没有历史会话)\n")
        return True

    choices = [
        questionary.Choice(title=_summary_line(mtime, prompt), value=sid)
        for sid, mtime, prompt in sessions
    ]
    async with in_terminal():
        selected = await questionary.select(
            "选择要恢复的会话（上下键移动，回车确认）：", choices=choices
        ).ask_async()
    # 用户按 Ctrl+C 取消选择
    if selected is None:
        return True

    # 还原对话历史，并把会话 ID 切换成选中的旧会话，后续消息继续追加到同一个文件
    state.history = session.load_history(selected)
    state.session_id = selected
    # 权限白名单是会话级的，切换会话后清空
    permissions.state.session_allowed.clear()
    # readFileState 也是会话级的，切换会话后换上新实例。恢复的历史里虽有读取痕迹，
    # 但进程退出后文件可能已变、mtime 不再可信，让模型恢复后首次编辑重读一次更稳
    state.read_file_state = ReadFileState()

    # jsonl 里每条模型回复都带 usage，把会话的 token 用量累加回来
    state.input_tokens = sum(
        m.usage.input_tokens for m in state.history if getattr(m, "kind", None) == "response"
    )
    state.output_tokens = sum(
        m.usage.output_tokens for m in state.history if getattr(m, "kind", None) == "response"
    )
    # 最近一轮的 API 调用记录只在进程内有效，没法恢复，清空
    state.last_api_calls.clear()

    # 把恢复的对话回放到屏幕上
    console.print(f"\n已恢复会话 {selected[:8]}，共 {len(state.history)} 条消息：\n")
    for msg in state.history:
        for part in msg.parts:
            # 回放和实时输出共用同一套 part 渲染逻辑
            print_part(part)
    console.print()
    return True


def cmd_status(state: SessionState) -> bool:
    console.print(f"模型：           {state.model_name}")
    console.print(f"权限模式：       {permissions.state.mode}")
    console.print(f"历史消息条数：    {len(state.history)}")
    console.print(f"累计输入 tokens：{state.input_tokens}")
    console.print(f"累计输出 tokens：{state.output_tokens}\n")
    return True


def cmd_api_detail(state: SessionState) -> bool:
    """
    显示最近一轮 user input 触发的所有 model API 调用元数据。
    """
    if not state.last_api_calls:
        console.print("(还没有任何模型调用记录，先发一条消息再来看)\n")
        return True

    console.print(f"最近一轮共发起 {len(state.last_api_calls)} 次 model API 调用\n")

    for i, call in enumerate(state.last_api_calls, 1):
        console.print(f"[bold]Call #{i}[/]")
        console.print("  Request:")
        console.print(f"    model:        {call.model}")
        console.print(f"    messages:     {call.messages_count} 条")
        if call.last_part is not None:
            preview = _format_part_line(call.last_part)
            if preview:
                console.print(f"    last_message: {preview}")
        console.print(f"    tools:        {', '.join(call.tools)}")
        console.print("  Response:")
        console.print(f"    finish_reason: {call.finish_reason}")
        console.print(f"    parts:         {', '.join(call.parts_kinds)}")
        console.print(f"    usage:         input={call.input_tokens}, output={call.output_tokens}")
        console.print()
    return True


COMMANDS = {
    "new": Command("new", "开启新会话", cmd_new),
    "resume": Command("resume", "恢复历史会话", cmd_resume),
    "status": Command("status", "显示当前会话状态", cmd_status),
    "api-detail": Command("api-detail", "显示最近一轮 model API 调用详情", cmd_api_detail),
    "help": Command("help", "显示可用命令", cmd_help),
    "exit": Command("exit", "退出程序", cmd_exit),
}
