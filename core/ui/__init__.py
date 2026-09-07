"""
终端 UI 层：渲染原语（render）、斜杠命令（commands）。

直接从子模块导入（core.ui.render / core.ui.commands）。这个 __init__ 故意不做任何重导出：
render 是底层原语，在这里重导出 commands 可能形成循环导入。
"""
