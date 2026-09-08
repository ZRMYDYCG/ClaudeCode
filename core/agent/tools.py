"""
Coding Agent 用到的三个工具：读文件、写文件、跑 shell 命令。

每个工具自己处理已知错误：能靠换参数纠正的（路径不存在、没权限）抛 ModelRetry
让模型重试，不能纠正的（二进制文件、命令出错）直接返回错误信息。
意料之外的异常由 hooks 里的 on_tool_execute_error 统一兜底。
"""

import subprocess

from pydantic_ai.exceptions import ModelRetry


def read_file(path: str) -> str:
    """
    读取指定文件的内容。
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError as e:
        raise ModelRetry(f"文件 {path} 不存在，请确认路径或换一个文件") from e
    except PermissionError as e:
        raise ModelRetry(f"没有权限读取 {path}，请换一个可读的文件") from e
    except IsADirectoryError as e:
        raise ModelRetry(f"{path} 是一个目录，请指定目录下的具体文件") from e
    except UnicodeDecodeError:
        return f"错误：{path} 不是文本文件，无法读取"


def write_file(path: str, content: str) -> str:
    """
    将内容写入指定文件。
    """
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入 {path}"
    except FileNotFoundError as e:
        raise ModelRetry(f"目录不存在，无法写入 {path}，请换一个已存在的目录") from e
    except PermissionError as e:
        raise ModelRetry(f"没有权限写入 {path}，请换一个可写的路径") from e
    except OSError as e:
        return f"错误：写入 {path} 失败 ({e})"


def run_command(command: str) -> str:
    """
    执行一条 shell 命令并返回输出。
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, errors="replace", timeout=10
        )
        output = result.stdout
        if result.returncode != 0:
            output += f"\n[错误] {result.stderr}"
        return output or "(无输出)"
    except subprocess.TimeoutExpired:
        return "[错误] 命令执行超时（10秒）"
    except OSError as e:
        return f"[错误] 无法执行命令 ({e})"


# Pydantic AI 支持 tools=[plain_function]，从函数签名 + docstring 自动生成 JSON Schema
TOOLS = [read_file, write_file, run_command]
