"""
挂在 Agent 上的 hooks：
1. API 调用元数据记录（/api-detail 命令用）
2. system-reminder 注入（每次 model 请求前，把过期文件提醒追加进 messages）
3. API 请求失败时的自动重试（wrap_model_request）
4. 工具调用权限检查（on_tool_execute）
5. 工具执行异常的兜底处理（on_tool_execute_error）
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.capabilities import Hooks
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import ModelRequest, UserPromptPart

from core import classifier, permissions
from core.ui.render import console, print_step

from .file_state import ReadFileState
from .reminders import build_reminder_text

MAX_RETRIES = 3


@dataclass
class ApiCall:
    """
    一次 model API 调用的元数据。before_model_request 创建并填充上半部分，
    after_model_request 填充下半部分。
    """

    # request 侧
    model: str
    messages_count: int
    # 这次发送给模型的 messages 中最后一条消息的最后一个 part
    last_part: Any
    tools: list[str]
    # response 侧（after hook 填充）
    finish_reason: str = ""
    parts_kinds: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


# 主循环在每轮 agent.iter() 之前清空它
api_call_log: list[ApiCall] = []

hooks = Hooks()


# ---------- API 调用记录 ----------


@hooks.on.before_model_request
async def _record_request(ctx: Any, request_context: Any) -> Any:
    """
    每次发起 model 调用之前，创建一条 ApiCall 记录。
    """
    msgs = list(request_context.messages)
    last_part = msgs[-1].parts[-1] if msgs and msgs[-1].parts else None
    try:
        tool_names = [t.name for t in request_context.model_request_parameters.function_tools]
    except AttributeError:
        tool_names = []
    api_call_log.append(
        ApiCall(
            model=request_context.model.model_name,
            messages_count=len(msgs),
            last_part=last_part,
            tools=tool_names,
        )
    )
    return request_context


@hooks.on.after_model_request
async def _record_response(ctx: Any, *, request_context: Any, response: Any) -> Any:
    """
    每次 model 调用返回后，填充上面这条 ApiCall 的 response 字段。
    """
    if api_call_log:
        call = api_call_log[-1]
        call.finish_reason = str(response.finish_reason) if response.finish_reason else "unknown"
        call.parts_kinds = [p.part_kind for p in response.parts]
        call.input_tokens = response.usage.input_tokens
        call.output_tokens = response.usage.output_tokens
    return response


# ---------- system-reminder 注入 ----------


@hooks.on.before_model_request
async def _inject_reminders(ctx: Any, request_context: Any) -> Any:
    """
    每次 model 请求前，readFileState 里有被外部改过的文件就追加一条 system-reminder；
    模型重读后 record() 刷新 timestamp，下次 hook 自然不再注入。
    """
    state: ReadFileState = ctx.deps
    text = build_reminder_text(state)
    if text is None:
        return request_context

    # 提醒只追加进这一次请求的 messages，不写回对话历史：
    # 会话文件、回放、下一轮请求都不会带上它，是纯粹发给模型看的临时信息
    reminder = ModelRequest(parts=[UserPromptPart(content=text)])
    new_messages = list(request_context.messages) + [reminder]
    print_step("[dim]◇ system[/]", f"[dim]{text[:200]}[/]")
    # ModelRequestContext 是 dataclass，官方推荐的修改方式就是 replace 出新实例
    return dataclasses.replace(request_context, messages=new_messages)


# ---------- API 请求重试 ----------


@hooks.on.model_request
async def _retry_on_error(ctx: Any, *, request_context: Any, handler: Any) -> Any:
    """
    包裹 model 请求，遇到可重试错误时自动指数退避重试。

    重试在 wrap 内部完成，对话历史和 before/after hooks 不受影响。
    兼容网关偶发的 UnexpectedModelBehavior（响应 schema 不对）也会重试。
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await handler(request_context)
        except ModelHTTPError as e:
            if e.status_code < 500:
                raise
            if attempt >= MAX_RETRIES:
                console.print(f"[bold red]✗ HTTP {e.status_code}，重试 {MAX_RETRIES} 次后仍失败[/]")
                raise
            wait = 2**attempt
            console.print(
                f"[bold yellow]⟳ HTTP {e.status_code}，{wait}s 后重试 "
                f"({attempt + 1}/{MAX_RETRIES})...[/]"
            )
            await asyncio.sleep(wait)
        except UnexpectedModelBehavior as e:
            if attempt >= MAX_RETRIES:
                console.print(f"[bold red]✗ 模型响应异常，重试 {MAX_RETRIES} 次后仍失败：{e}[/]")
                raise
            wait = 2**attempt
            console.print(
                f"[bold yellow]⟳ 模型响应异常，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})...[/]"
            )
            await asyncio.sleep(wait)
        except ModelAPIError:
            if attempt >= MAX_RETRIES:
                console.print(f"[bold red]✗ 网络连接失败，重试 {MAX_RETRIES} 次后仍无法连接[/]")
                raise
            wait = 2**attempt
            console.print(
                f"[bold yellow]⟳ 网络连接失败，{wait}s 后重试 ({attempt + 1}/{MAX_RETRIES})...[/]"
            )
            await asyncio.sleep(wait)

    raise RuntimeError("unreachable")  # pragma: no cover


# ---------- 工具调用权限检查 ----------


@hooks.on.tool_execute
async def _check_permission(ctx: Any, *, call: Any, tool_def: Any, args: Any, handler: Any) -> Any:
    """
    工具执行前的权限关卡。allow 就调用 handler 真正执行；
    ask 就弹审批列表；deny 则把拒绝原因当作工具结果回填，让模型自行纠正。
    auto 模式下，ask 不直接弹窗，先交给 LLM classifier 判定。
    """
    decision = permissions.compute_decision(call.tool_name, args)
    if decision == "allow":
        # 放行，handler(args) 才是真正执行工具的那一步
        return await handler(args)

    # decision == "ask" 且当前是 auto 模式：让 classifier 替用户做决定
    if permissions.state.mode == permissions.AUTO:
        # 审查过程对齐成和 thinking、tool_call 一样的「图标 + 标签独占一行、内容换行」格式
        # 用蓝色让用户一眼看到 classifier 在工作
        print_step("[blue]◆ auto_check[/]", f"[blue dim]正在请 LLM 审查 {call.tool_name}...[/]")
        verdict = await classifier.classify(ctx.messages, call.tool_name, args)

        if verdict.get("error"):
            # classifier 自己出错，回退到下面的人工审批弹窗，不能因为审查失败就放行
            print_step("[yellow]⚠ auto_check[/]", f"[yellow]{verdict['reason']}[/]")
        elif not verdict["should_block"]:
            # classifier 判定安全，放行执行，并把理由打出来让用户随时能审计；标签用 ✔ 表示放行
            print_step("[blue]✔ auto_check[/]", f"[blue dim]放行：{verdict['reason']}[/]")
            return await handler(args)
        else:
            # classifier 判定危险：和人工拒绝一样回填给模型，多带上一句拦截理由；标签用 ✘ 表示拦截
            print_step("[red]✘ auto_check[/]", f"[red]拦截：{verdict['reason']}[/]")
            return (
                f"安全检查拦截了这次 {call.tool_name} 调用，没有执行。"
                f"拦截理由：{verdict['reason']}。"
                "不要尝试绕过拦截，请停下来向用户说明情况，由用户决定接下来怎么做。"
            )

    # default / acceptEdits 模式的 ask，或 auto 模式下 classifier 出错的回退：弹审批让用户决定
    choice = await permissions.prompt_approval(call.tool_name, args)
    if choice == "once":
        return await handler(args)
    if choice == "always":
        # 记进会话白名单，本会话内这个工具不再询问
        permissions.state.session_allowed.add(call.tool_name)
        return await handler(args)

    # 拒绝：不执行工具，把拒绝原因回填给模型，让它停下来等用户发话，而不是自作主张绕过去
    return (
        f"用户拒绝了对 {call.tool_name} 的调用，这次调用没有执行。"
        "请停下手上的事，等用户告诉你接下来该怎么做。"
    )


# ---------- 工具执行异常兜底 ----------


@hooks.on.tool_execute_error
async def _handle_tool_error(
    ctx: Any, *, call: Any, tool_def: Any, args: Any, error: Exception
) -> str:
    """
    工具函数抛出未捕获异常时，不让进程崩溃，
    而是把错误信息作为 tool result 返回给模型，让它自行纠正。
    """
    console.print(f"[bold red]✗ 工具 {call.tool_name} 出错：{error}[/]")
    return f"工具执行出错：{type(error).__name__}: {error}"
