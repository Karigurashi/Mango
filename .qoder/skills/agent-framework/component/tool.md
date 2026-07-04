# ToolComponent 工具系统

工具注册、发现、调度、统计的总线。内置工具、Skill 加载工具、MCP 远程工具最终都汇集到这里。

## BaseTool 基类

每个工具是 BaseTool 的子类，类属性声明元信息，实例方法实现执行逻辑。

### 双轨执行

```
ExecuteAsync(**kwargs) → ToolResult
├── _InvokeAsync 已重写 → 直接 await
└── 仅重写 _Invoke → asyncio.to_thread 包同步逻辑
```

优先 `_InvokeAsync`，同时实现时以 `_InvokeAsync` 为准。

### 关键类属性

| 属性 | 说明 |
|------|------|
| name | 工具名（function calling 唯一标识） |
| description | LLM 语义说明 |
| parameters | JSON Schema |
| timeout | 单次执行超时（None 不设限） |
| resultLodLevel | 结果默认 LOD 等级 |
| skipPersist | 是否跳过落盘判定 |
| _agent | 调度前由 ToolComponent 自动注入 Agent 引用 |

## @Register 装饰器

把工具类写入类级共享的 `_toolClasses[name]`，仅注册类不实例化。`toolComponent.py` 文件末尾 import 触发 @Register，不需要显式 LoadBuiltins。

## ToolResult

不可变 NamedTuple：success + content + error。快捷工厂：`ToolResult.Ok(content)` / `ToolResult.Fail(error)`。`ToLLMContent()` 返回注入 LLM 的文本。

## ToolComponent 调度

- **类级共享 / 实例级隔离**：`_toolClasses` 全进程一份（@Register 写入），`_tools` 每 Agent 一份。
- **DispatchAsync(toolCall)**：注入 agent 引用 → 三级超时解析 → asyncio.wait_for → 记录统计。
- **DispatchBatchAsync(toolCalls)**：并发 gather，单工具失败不取消其余。
- 任意异常包装为 ToolResult.Fail，不抛出主循环。

### 超时三级优先级

工具实例 timeout > 工具类 timeout > _defaultTimeout（300s 兜底）。

### 执行统计

每工具独立 deque（maxlen=100），GetExecutionStats() 返回 {count, avg, max, min, last}。

## 内置工具清单

| 分类 | 工具 | 说明 |
|------|------|------|
| FILE | read_file | 读文件（支持行范围） |
| FILE | write_file | 原子写入 |
| FILE | glob | glob 模式查找文件 |
| FILE | grep_code | ripgrep 风格全文检索 |
| FILE | search_codebase | 语义代码搜索 |
| FILE | search_replace | 字符串替换编辑 |
| FILE | delete_file | 安全删除文件 |
| SHELL | shell | Shell 命令执行 |
| SHELL | get_terminal_output | 后台终端输出 |
| NETWORK | web_fetch | HTTP GET / 网页提取 |
| NETWORK | web_search | 搜索引擎查询 |
| CONTROL | todo_write | 任务清单写入 |
| CONTROL | fetch_rules | 规则内容获取 |
