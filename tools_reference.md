# Agent 工具定义清单

## 1. Read
**描述**: 读取本地文件系统上的文件。可以访问任何文件，支持读取整个文件或指定行范围。支持读取图片文件（jpeg/jpg, png, webp）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件的绝对路径 |
| `start_line` | integer | 否 | 起始行号（1-based，包含） |
| `end_line` | integer | 否 | 结束行号（1-based，包含） |

---

## 2. Write
**描述**: 创建新文件或修改现有文件。文件内容限制最多 1000 行。支持分部分写入（append 模式）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件的绝对路径 |
| `file_content` | string | 是 | 文件内容 |
| `add_last_line_newline` | boolean | 否 | 是否在末尾添加换行（默认 true） |
| `append` | boolean | 否 | 是否追加到已有文件（默认 false） |
| `continuation_context` | string | 否 | 前次截断写入的最后3行，用于验证追加位置 |

---

## 3. SearchReplace
**描述**: 在文件中进行精确字符串替换。支持一次调用中进行多个替换操作。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件绝对路径（文件必须存在） |
| `replacements` | array | 是 | 替换操作数组，每个元素包含： |
| `replacements[].original_text` | string | 是 | 要被替换的原文本（必须在文件中唯一匹配） |
| `replacements[].new_text` | string | 是 | 替换后的新文本（必须与原文本不同） |
| `replacements[].replace_all` | boolean | 否 | 是否替换所有匹配项（默认 false） |

---

## 4. DeleteFile
**描述**: 安全删除文件。只能通过此工具删除，不能使用 shell 命令。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_path` | string | 是 | 文件的绝对路径 |

---

## 5. Glob
**描述**: 按 glob 模式搜索文件，只返回匹配文件的路径。限制最多 2000 个结果。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | Glob 匹配模式（如 `*.go`, `**/test/*.py`） |
| `path` | string | 否 | 搜索目录路径（省略则从工作区根目录搜索） |

---

## 6. SearchCodebase
**描述**: 语义化代码搜索，按含义而非精确文本查找代码。适用于不知道哪些文件包含所需信息时。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 简洁的、关键词丰富的搜索字符串 |
| `key_words` | string | 是 | 从查询中提取的最多3个最重要关键词，逗号分隔 |
| `target_directories` | array[string] | 否 | 绝对目录路径数组，用于缩小搜索范围 |

---

## 7. Grep
**描述**: 高性能文件内容搜索（ripgrep 引擎），支持正则表达式。结果自动展开为完整语法块。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `regex` | string | 是 | 搜索的正则表达式 |
| `path` | string | 否 | 目标文件或目录路径 |
| `type` | string | 否 | 文件类型（如 js, py, rust, go, java） |
| `glob` | string | 否 | 文件过滤 glob 模式 |
| `-i` | boolean | 否 | 是否忽略大小写（默认 false） |
| `-A` | number | 否 | 匹配后显示的上下文行数 |
| `-B` | number | 否 | 匹配前显示的上下文行数 |
| `-C` | number | 否 | 匹配前后显示的上下文行数 |
| `multiline` | boolean | 否 | 是否启用多行匹配（默认 false） |

---

## 8. LSP
**描述**: 语言服务器协议工具，提供代码智能功能（跳转定义、查找引用等）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `operation` | enum | 是 | 操作类型：`goToDefinition`, `findReferences`, `hover`, `documentSymbol`, `workspaceSymbol`, `goToImplementation`, `prepareCallHierarchy`, `incomingCalls`, `outgoingCalls` |
| `filePath` | string | 条件 | 文件绝对/相对路径（除 workspaceSymbol 外必需） |
| `line` | integer | 条件 | 行号（1-based，除 workspaceSymbol/documentSymbol 外必需） |
| `character` | integer | 条件 | 字符偏移（1-based，除 workspaceSymbol/documentSymbol 外必需） |
| `query` | string | 条件 | workspaceSymbol 时的符号名搜索 |
| `maxResults` | integer | 否 | 最大返回符号数 |
| `includeContent` | boolean | 否 | 是否包含依赖内容（workspaceSymbol 默认 false，其他默认 true） |
| `contentMaxChars` | integer | 否 | 每个结果最大内容字符数 |

---

## 9. Bash
**描述**: 在终端执行 shell 命令。用于 git、npm、docker 等终端操作，不用于文件操作。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `command` | string | 是 | 要执行的 shell 命令 |
| `is_background` | boolean | 是 | 是否后台运行 |
| `timeout` | integer | 否 | 超时时间（毫秒，默认 180000，最大 1800000） |
| `command_names` | array[string] | 否 | 命令中解析出的命令名 |
| `has_risk` | boolean | 否 | 命令是否有潜在风险 |
| `required_permissions` | string | 否 | 设为 `'all'` 可在沙箱外运行 |

---

## 10. GetTerminalOutput
**描述**: 获取之前启动的终端命令的输出。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `terminal_id` | string | 是 | 终端命令的 ID |
| `wait_seconds` | integer | 否 | 等待命令完成的时间（默认 2s） |

---

## 11. GetProblems
**描述**: 获取代码文件中的编译或 lint 错误。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_paths` | array[string] | 是 | 文件的绝对路径数组 |

---

## 12. TodoWrite
**描述**: 创建和管理任务列表，用于跟踪复杂多步骤任务。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `merge` | boolean | 是 | true=按 id 合并, false=替换所有 |
| `todos` | array | 是 | 任务项数组，每项包含： |
| `todos[].id` | string | 是 | 唯一标识符 |
| `todos[].content` | string | 是 | 任务描述（建议 ≤70 字符） |
| `todos[].status` | enum | 是 | 状态：`PENDING`, `IN_PROGRESS`, `COMPLETE`, `CANCELLED` |

---

## 13. AskUserQuestion
**描述**: 在执行过程中向用户提问，收集偏好或澄清指令。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `questions` | array | 是 | 问题数组（1-4个问题），每个包含： |
| `questions[].question` | string | 是 | 完整问题文本 |
| `questions[].options` | array | 是 | 选项数组（2-4个），每个含 `label` 和 `description` |
| `questions[].header` | string | 否 | 短标签（最多12字符） |
| `questions[].multiSelect` | boolean | 否 | 是否允许多选 |

---

## 14. SwitchMode
**描述**: 切换交互模式以更好匹配当前任务。只能切换到 `plan` 模式。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target_mode_id` | string | 是 | 目标模式，允许值：`'plan'` |

---

## 15. CreatePlan
**描述**: 创建或更新计划。支持三种模式：write（新建）、notify_update（通知更新）、rewrite（重写现有）。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | enum | 是 | 操作模式：`write`, `notify_update`, `rewrite` |
| `name` | string | 条件 | 计划短名称（3-4词，write 模式必填） |
| `overview` | string | 是 | 1-2句高级描述 |
| `plan` | string | 条件 | Markdown 格式的详细计划内容（write/rewrite 模式必填） |

---

## 16. Agent
**描述**: 启动专门的子代理来处理复杂任务。可用类型：Browser, CodeReview, ComputerUse, Debug, Guide。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `subagent_type` | enum | 是 | 子代理类型：`Browser`, `CodeReview`, `ComputerUse`, `Debug`, `Guide` |
| `description` | string | 是 | 任务简短描述（3-5词） |
| `prompt` | string | 是 | 子代理要执行的任务描述 |

---

## 17. Skill
**描述**: 在主对话中执行技能。可用技能：canvas, create-skill, create-subagent, vercel-deploy。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `skill` | string | 是 | 技能名称 |
| `args` | string | 否 | 传递给技能的可选参数 |

---

## 18. WebFetch
**描述**: 从网页获取主要内容。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | HTTP/HTTPS URL |
| `query` | string | 否 | 在页面内容中搜索的查询 |

---

## 19. WebSearch
**描述**: 探索网络获取实时信息。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索查询（1-100字符） |
| `timeRange` | enum | 否 | 时间范围：`OneDay`, `OneWeek`, `OneMonth`, `OneYear`, `NoLimit` |

---

## 20. FetchRules
**描述**: 查询规则的详细内容。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rule_names` | array[string] | 是 | 要获取的规则名称数组 |

---

## 21. CallMcpTool
**描述**: 调用 MCP 服务器提供的工具。调用前必须先读取工具的 JSON schema 文件。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `server_name` | string | 是 | MCP 服务器名称 |
| `tool_name` | string | 是 | 工具名称 |
| `arguments` | object | 是 | 传递给工具的参数 |

---

## 22. UpdateMemory
**描述**: 基于用户意图创建、更新或删除记忆。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 记忆标题 |
| `usage_scenario` | array[string] | 是 | 使用场景数组 |
| `content` | string | 是 | 记忆内容 |
| `keywords` | string | 是 | 关键词，逗号分隔 |
| `category` | enum | 是 | 记忆类别（如 `user_info`, `project_tech_stack`, `learned_skill_experience` 等） |
| `action` | enum | 是 | 操作类型：`create`, `update`, `delete` |
| `source` | enum | 是 | 来源：`user` 或 `auto` |
| `scope` | string | 否 | 范围：`global` 或 `workspace` |
| `id` | string | 否 | 已有记忆的 ID（update/delete 时必填） |

---

## 23. SearchMemory
**描述**: 检索详细记忆和知识。支持三种模式：fetch、search、explore。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | enum | 是 | 检索模式：`fetch`（精确获取）, `search`（关键词搜索）, `explore`（逐层浏览） |
| `query` | string | 是 | 查询内容（fetch=精确标题，search=查询描述，explore=逗号分隔路径） |
| `keywords` | string | 否 | search 模式的关键词（最多5个，逗号分隔） |
| `category` | string | 否 | search 模式的记忆类别 |

---

## 24. RunPreview
**描述**: 为 Web 服务器设置预览浏览器。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 目标 Web 服务器的 URL（含 scheme 和 port） |
| `name` | string | 否 | 短名称（3-5词，Title-Case） |
