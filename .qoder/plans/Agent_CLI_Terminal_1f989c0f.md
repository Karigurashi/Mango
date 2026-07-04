# Agent CLI Terminal 实现计划

## 架构总览

在 `agent/cli/` 下构建 9 个文件的框架性 CLI 模块，对标 Claude Code CLI 的交互模式：

```
agent/cli/
├── __init__.py               # 包导出
├── __main__.py               # python -m agent.cli 入口
├── eCliState.py              # CLI 状态机枚举
├── cliConfig.py              # ANSI 主题/显示限制配置
├── cliRenderer.py            # 事件→终端实时渲染引擎
├── cliCommand.py             # CliCommand + CliContext
├── cliCommandRegistry.py    # 斜杠指令注册与分发
├── builtinCommands.py        # 内置指令实现
└── cliApp.py                 # REPL 主编排器
```

## Task 1: ECliState 状态枚举 — `eCliState.py`

```python
class ECliState(IntEnum):
    IDLE = 0          # 等待用户输入
    RUNNING = 1       # Agent 执行中
    CANCELLING = 2    # Ctrl+C 已触发，等待优雅停止
    EXITING = 3       # 应用关闭中
```

## Task 2: CliConfig 配置 — `cliConfig.py`

`@dataclass(slots=True)` 配置类，包含：
- ANSI 颜色/样式常量（RESET/BOLD/DIM/ITALIC/RED/GREEN/YELLOW/BLUE/CYAN/GRAY）
- 显示限制：`maxToolResultLines=20`、`maxToolArgsDisplay=200`、`showThinking=True`、`showTokenCount=True`
- 辅助方法：`Color(text, color)`、`Dim(text)`、`Bold(text)`、`Truncate(text, maxLines)`
- 工具图标：thinking=`✻`、text=`⏺`、tool=`⚡`、error=`✗`、compact=`↻`

## Task 3: CliRenderer 渲染引擎 — `cliRenderer.py`

**核心职责**：订阅 EventBusComponent 事件，实时渲染到终端。

**设计要点**：
- 使用 `sys.stdout.write()` + `sys.stdout.flush()` 精细控制输出
- 事件对象池感知：OnEvent 回调中立即提取数据，不持有 event 引用
- 模式切换状态机：`_inThinking` / `_inText` / `_inTool` 控制输出样式

**事件映射表**：

| 事件 | 渲染行为 |
|------|----------|
| TURN_START | 首轮不输出，后续轮打印 `── Turn {n} ──` 分隔线 |
| THINKING_DELTA | 切换到 thinking 模式，首行打 `✻` 前缀，内容 DIM+ITALIC |
| THINKING_COMPLETE | 关闭 thinking 块，打印空行 |
| TEXT_DELTA | 切换到 text 模式，首行打 `⏺` 前缀，内容正常色 |
| TEXT_COMPLETE | 关闭 text 块，打印空行 |
| TOOL_START | `⚡ {toolName}({truncatedArgs})` CYAN 色 |
| TOOL_RESULT | 缩进 GRAY 色，截断至 maxToolResultLines 行 |
| STATE_CHANGE | 状态映射：THINKING→无输出、ACTING→无输出、FINISHED→无输出、ERROR→无输出 |
| COMPACTION | `↻ {content}` YELLOW 色 |
| ERROR | `✗ {error}` RED 色 |
| DONE | 打印空行分隔，重置模式状态 |

**性能策略**：
- delta 事件直接 `sys.stdout.write(content)`，不拼接字符串
- 工具结果按行截断，超限显示 `... ({n} more lines)`
- 模式切换时打印前缀和颜色代码，退出时打印 RESET

## Task 4: CliCommand + CliContext — `cliCommand.py`

**CliCommand** `@dataclass`:
- `name: str` — 指令名（不含 `/`）
- `description: str` — 简短描述
- `handler: Callable[[CliContext, str], Awaitable[None]]` — 异步处理函数
- `aliases: list[str]` — 别名列表

**CliContext** — 命令处理器上下文，提供组件访问：
- `Agent` → Agent 实例
- `Session` → SessionComponent（通过 GetComponent）
- `LLM` → LLMComponent
- `Context` → ContextComponent
- `Tools` → ToolComponent
- `Config` → CliConfig
- `Print(text)` / `PrintDim(text)` — 便捷输出方法

## Task 5: CliCommandRegistry 注册分发 — `cliCommandRegistry.py`

```python
class CliCommandRegistry:
    def Register(self, command: CliCommand) -> None
    async def DispatchAsync(self, input: str, context: CliContext) -> bool  # 返回是否匹配到命令
    def GetHelpText(self) -> str  # 格式化帮助文本
    def GetCommands(self) -> list[CliCommand]
```

- 输入解析：`/command arg1 arg2` → name=`command`, args=`arg1 arg2`
- 别名支持：`/quit` → `/exit`
- 未知命令提示：`Unknown command: /xxx. Type /help for available commands.`

## Task 6: 内置指令 — `builtinCommands.py`

`RegisterBuiltinCommands(registry: CliCommandRegistry)` 函数注册以下指令：

| 指令 | 别名 | 行为 |
|------|------|------|
| `/help` | `/h` | 打印所有可用指令及描述 |
| `/clear` | `/c` | 调用 `SessionComponent.NewSession()`，打印确认 |
| `/compact` | - | `await Context.CompactAsync(force=True)`，打印结果 |
| `/model` | `/m` | 无参数：列出 `LLMManager.ListModels()` + 当前模型；有参数：切换模型 |
| `/cost` | - | 打印 `LLM.TotalPromptTokens / TotalCompletionTokens / LastCacheHitRate` |
| `/status` | `/s` | 打印 Agent 状态、模型名、Session ID、消息数、估算 Token、工具数 |
| `/sessions` | - | 列出 `SessionComponent.GetSessionIds()`，标记活跃 |
| `/session` | - | `/session <id>` → `SessionComponent.SwitchSession(id)` |
| `/tools` | `/t` | 按 EToolCategory 分组列出 `ToolComponent.GetAll()` |
| `/config` | - | 打印 `DataComponent.config` 关键配置项 |
| `/exit` | `/quit` `/q` | 设置 `ECliState.EXITING` |

**模型切换实现**：
1. `LLMManager.GetProvider(newModelName)` 获取新 LLM
2. `agent._dataComp.llm = newLlm` 替换 DataComponent 持有
3. `llmComp.llm = newLlm` 替换 LLMComponent 持有（已有 setter）
4. 打印确认信息

## Task 7: CliApp 主编排器 — `cliApp.py`

**核心流程**：
```
__init__:
  1. LLMManager.EnsureLoaded() (通过 CreateAgent 触发)
  2. AgentManager.CreateAgent(modelName) → Agent 实例
  3. CliConfig 初始化
  4. CliRenderer 初始化
  5. Agent.GetComponent(EventBusComponent).Subscribe(renderer.OnEvent)
  6. CliCommandRegistry 初始化 + RegisterBuiltinCommands
  7. ECliState = IDLE

RunAsync:
  1. PrintBanner() — 打印 Brain CLI 欢迎横幅（模型名、会话ID、指令提示）
  2. while state != EXITING:
     a. signal.signal(SIGINT, default_int_handler)  — 输入阶段恢复默认
     b. try: input = await asyncio.to_thread(input, prompt)
        except KeyboardInterrupt: break (退出)
        except EOFError: break
     c. if input.startswith('/'): await registry.DispatchAsync(input, context)
     d. else: await _RunAgentAsync(input)

_RunAgentAsync(message):
  1. state = RUNNING
  2. cancellationToken = CancellationToken()
  3. signal.signal(SIGINT, _OnInterrupt)  — 安装取消处理器
  4. try: await agent.RunStreamAsync(message, cancellationToken)
     except KeyboardInterrupt: pass  (已被 token 取消)
     finally:
       state = IDLE
       cancellationToken = None
       signal.signal(SIGINT, default_int_handler)

_OnInterrupt(signum, frame):
  if cancellationToken: cancellationToken.Cancel()
```

**Banner 设计**：
```
╭──────────────────────────────────────────────────╮
│  Brain Agent CLI                                  │
│  Model: deepseek-high  |  Session: #1             │
│  /help for commands  |  Ctrl+C to interrupt       │
╰──────────────────────────────────────────────────╯
```

**Prompt 构建**：`> `（简洁，Claude Code 风格）

## Task 8: __init__.py + __main__.py

**__init__.py**：
```python
from .cliApp import CliApp
from .cliConfig import CliConfig
from .cliRenderer import CliRenderer
from .cliCommand import CliCommand, CliContext
from .cliCommandRegistry import CliCommandRegistry
from .eCliState import ECliState
__all__ = [...]
```

**__main__.py**：
```python
import asyncio
from .cliApp import CliApp
def main():
    app = CliApp()
    asyncio.run(app.RunAsync())
if __name__ == "__main__":
    main()
```

支持 `python -m agent.cli` 启动。

## Task 9: workspace/start_cli.bat 启动脚本

参考 `start_chat.bat`，简化为：
```bat
@echo off
chcp 65001 >nul
title Brain Agent CLI
cd /d "%~dp0.."
py -3 -m agent.cli
pause
```

## 性能与内存设计要点

1. **零分配渲染**：delta 事件直接 `sys.stdout.write()`，不拼接中间字符串
2. **对象池感知**：renderer.OnEvent 提取数据后立即返回，不持有 event 引用（Push 后 event 被 Release）
3. **流式输出**：文本/思考链逐 chunk 输出，不缓冲完整响应
4. **CancellationToken 复用**：每轮创建新 token，旧 token 随 Agent 调用结束自然 GC
5. **Signal 切换**：输入阶段用默认 handler（KeyboardInterrupt），执行阶段用取消 handler，避免冲突
6. **StringIO 复用**：LLMComponent 内部已有 StringIO 缓冲区复用机制，renderer 层不需额外缓冲
7. **截断策略**：工具结果按行截断，工具参数按字符截断，避免终端 flooding

## 编码规范遵从

- 文件名 camelCase，一个文件一个核心类
- 方法 PascalCase，变量 camelCase，私有字段 _camelCase
- 枚举继承 IntEnum，文件名 e 前缀
- async 方法以 Async 结尾
- 显式类型声明，不使用 **kwargs
- Import 顺序：标准库 → 第三方 → 框架内部
