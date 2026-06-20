# RuleComponent 规则引擎

> 源码：[`agent/component/rule/ruleComponent.py`](../../../agent/component/rule/ruleComponent.py)、[`agent/component/rule/rule.py`](../../../agent/component/rule/rule.py)、[`agent/component/rule/eRuleTriggerMode.py`](../../../agent/component/rule/eRuleTriggerMode.py)

RuleComponent 对标 Cursor Rules / Claude Code Project Rules：把项目级**约束 / 偏好 / 规范**沉淀到 `.rule.md` 文件，按四种触发模式动态注入到 LLM 上下文。它和 [SkillComponent](skill.md) 互补：

* **Rule = "做事的边界"**（强制约束、命名规范、禁用 API）；
* **Skill = "做事的步骤"**（SOP、操作清单、自动化流程）。

## 1 模块结构

```
agent/component/rule/
├── rule.py             # Rule 数据类 + frontmatter 解析 + glob 转 regex
├── ruleComponent.py    # 运行时管理 + 四种触发模式匹配
└── eRuleTriggerMode.py # ERuleTriggerMode 枚举
```

## 2 Rule 数据结构（rule.py）

```text
@dataclass
Rule:
  ├─ name:         str                  # 唯一标识（kebab-case）
  ├─ description:  str                  # 给 LLM 看的语义说明
  ├─ triggerMode:  ERuleTriggerMode     # 见 §3
  ├─ globs:        list[str]            # GLOB_MATCH 模式的路径模式
  ├─ alwaysApply:  bool                 # 等价于 triggerMode=ALWAYS_APPLY 的 frontmatter 别名
  ├─ body:         str                  # 注入正文（Markdown）
  └─ sourcePath:   str                  # 来源 .rule.md 路径

工厂：
  Rule.FromMarkdown(source, sourcePath)
      ├─ 解析 YAML frontmatter
      ├─ 调用 _InferTriggerMode 推断 triggerMode（见 §3.1）
      └─ 编译 globs → 内部 regex 缓存

实例方法：
  MatchesGlob(filePath) -> bool         # 用预编译的 regex 命中
```

`.rule.md` 示例：

```markdown
---
name: no-print-debug
description: 禁止在生产代码中使用 print 调试
globs: ["src/**/*.py"]
---

代码里禁止使用 `print`，统一通过 Logger.* 输出。
```

## 3 触发模式（eRuleTriggerMode.py）

```text
ERuleTriggerMode (Enum):
    ALWAYS_APPLY        = "alwaysApply"        # 每次都注入 system
    GLOB_MATCH          = "globMatch"          # 当前涉及文件路径匹配 globs 时注入
    DESCRIPTION_MATCH   = "descriptionMatch"   # 用户输入与 description 语义相关时注入
    MANUAL_INVOKE       = "manualInvoke"       # 用户消息含 "@rule-name" 时注入
```

### 3.1 `_InferTriggerMode` 推断顺序

```text
_InferTriggerMode(frontmatter):
    if alwaysApply == True              ──► ALWAYS_APPLY
    elif globs not empty                 ──► GLOB_MATCH
    elif description not empty           ──► DESCRIPTION_MATCH
    else                                  ──► MANUAL_INVOKE
```

> 显式 `triggerMode` 字段优先；缺失时按以上顺序推断，对齐 Cursor Rules 行为。

### 3.2 `_GlobToRegex`

```text
*.py             → ^.*\.py$
src/**/*.py      → ^src/.*?/.*\.py$
?                → 单字符占位
[abc]            → 字符集
```

* 编译一次缓存到 Rule 实例，运行时 O(1) 匹配；
* 支持 Windows 反斜杠归一化（统一为 `/` 比较）。

## 4 RuleComponent（ruleComponent.py）

### 4.1 字段

```text
RuleComponent
  ├─ _rules:      dict[str, Rule]
  └─ _matchStats: dict[str, int]   # 每条 Rule 命中次数（观测）
```

### 4.2 主要方法

| 方法 | 用途 |
|------|------|
| `LoadFromDirectory(dir)` | 递归扫描 `*.rule.md`，调用 `Rule.FromMarkdown` 入库 |
| `Register(rule)` | 程序化注册 |
| `GetAlwaysApplyBody() -> str` | **Harness LOD0 注入用**：拼接所有 ALWAYS_APPLY Rule 的 body |
| `MatchGlobs(filePath) -> list[Rule]` | 返回 GLOB_MATCH 中命中该路径的 Rule |
| `MatchDescription(query) -> list[Rule]` | DESCRIPTION_MATCH 模式：基于关键词命中（见 §5） |
| `MatchManualInvoke(text) -> list[Rule]` | 解析 `@rule-name` 引用，返回对应 Rule |
| `GetMatchedBody(...) -> str` | 高层便利：合并多种匹配结果的正文 |
| `GetStats() -> dict` | 命中统计 |

### 4.3 ALWAYS_APPLY 注入

由 HarnessComponent.BuildAsync 在 LOD0 阶段调用：

```text
blocks.append(rule.GetAlwaysApplyBody())   # 多个 Rule 用 

---

 分隔
```

整个 Run 期间常驻 system 头部，永不压缩。

## 5 四种触发模式实现细节

### 5.1 ALWAYS_APPLY

```text
GetAlwaysApplyBody():
    parts = []
    for r in _rules.values():
        if r.triggerMode == ALWAYS_APPLY:
            parts.append(f"## Rule: {r.name}\n{r.body}")
            _matchStats[r.name] += 1
    return "\n\n---\n\n".join(parts)
```

### 5.2 GLOB_MATCH

```text
MatchGlobs(filePath):
    return [r for r in _rules.values()
              if r.triggerMode == GLOB_MATCH and r.MatchesGlob(filePath)]
```

* 由调用方（如代码编辑工具或 Agent 主循环）传入当前涉及文件路径；
* 命中后通常作为 system 消息追加到下一轮上下文。

### 5.3 DESCRIPTION_MATCH

```text
MatchDescription(query):
    keywords = _Tokenize(query)            # 简单 lower + 中英文分词
    return [r for r in _rules.values()
              if r.triggerMode == DESCRIPTION_MATCH
              and _ContainsAny(r.description, keywords)]
```

> 简单关键词匹配；语义模型可由调用方替换。

### 5.4 MANUAL_INVOKE

```text
MatchManualInvoke(text):
    # 用正则 r"@([\w-]+)" 抽取所有 @name 引用
    names = re.findall(r"@([\w-]+)", text)
    return [_rules[n] for n in names if n in _rules
                                      and _rules[n].triggerMode == MANUAL_INVOKE]
```

## 6 与其他组件的关系

| 组件 | 调用 |
|------|------|
| HarnessComponent | `LoadFromDirectory` + `GetAlwaysApplyBody`（LOD0 注入） |
| ContextComponent | 调 `MatchGlobs/MatchDescription/MatchManualInvoke` 把命中正文作为 LOD0/LOD1 注入下一轮 |
| SkillComponent | 互不依赖 |

## 7 关键不变式

1. **`triggerMode` 在 Rule 加载后冻结**——避免运行时改变导致的注入策略漂移。
2. **`_GlobToRegex` 编译缓存**：每条 Rule 的 globs 只编译一次，运行时匹配是纯字符串比较。
3. **匹配命中累加 `_matchStats`**：可通过日志或诊断接口观测哪些 Rule 频繁触发，决定是否升级为 ALWAYS_APPLY。
4. **`MANUAL_INVOKE` 的 Rule 不会被自动注入**——必须用户/Agent 显式 `@name`，避免静默改变行为。
