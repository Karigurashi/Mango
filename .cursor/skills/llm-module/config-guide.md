# models.json 配置指南

## 完整示例

```json
{
    "models": [
        {
            "name": "deepseek-high",
            "provider": "openai",
            "url": "https://api.deepseek.com/v1",
            "apiKey": "sk-xxx",
            "modelName": "deepseek-reasoner",
            "timeout": 120,
            "maxRetries": 3,
            "tier": "high"
        },
        {
            "name": "deepseek-mid",
            "provider": "openai",
            "url": "https://api.deepseek.com/v1",
            "apiKey": "sk-xxx",
            "modelName": "deepseek-chat",
            "timeout": 120,
            "maxRetries": 3,
            "tier": "mid"
        },
        {
            "name": "deepseek-low",
            "provider": "openai",
            "url": "https://api.deepseek.com/v1",
            "apiKey": "sk-xxx",
            "modelName": "deepseek-chat",
            "timeout": 120,
            "maxRetries": 3,
            "tier": "low"
        },
        {
            "name": "claude-3",
            "provider": "anthropic",
            "url": "https://api.anthropic.com/v1",
            "apiKey": "sk-ant-xxx",
            "modelName": "claude-3-opus-20240229",
            "thinkingBudget": 8000,
            "timeout": 90,
            "tier": "high"
        }
    ],
    "defaultModel": "deepseek-high"
}
```

## 字段说明

| 字段 | 必填 | 说明 |
|------|:--:|------|
| `name` | ✓ | 调度时的唯一标识，如 `"deepseek-high"` |
| `url` | ✓ | API base URL（Gemini 可为空字符串 `""`） |
| `apiKey` | ✓ | 认证密钥 |
| `provider` | | `"openai"` / `"anthropic"` / `"gemini"`，缺失时从 url 自动推断 |
| `modelName` | | 实际模型名，缺失时沿用 name |
| `tier` | | 档位：`"high"` / `"mid"` / `"low"`，用于 `GetClientByTier` 调度 |
| `timeout` | | 超时秒数，默认 120 |
| `maxRetries` | | 最大重试次数，默认 2 |
| `thinkingBudget` | | 仅 Anthropic，Extended Thinking 预算 token，默认 4000 |

## Provider 自动推断

当 `provider` 字段缺失时，根据 `url` 自动判断：

| url 包含 | 推断为 |
|----------|--------|
| `anthropic` | `anthropic` |
| `gemini` 或 `google` | `gemini` |
| 其他 | `openai` |

## 同档多模型

tier 映射取第一个匹配的模型。例如两个模型都配置 `"tier": "high"`，`GetClientByTier(ETier.HIGH)` 返回先注册的那个。
