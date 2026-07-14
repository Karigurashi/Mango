# 飞书卡片与流式打字机

## 权限

| 权限标识 | 说明 |
|---|---|
| `im:message` / `im:message:send_as_bot` | 发送卡片消息 |
| `im:message:update` | 更新已发送的卡片 |
| `cardkit:card:write` | 创建与更新卡片（流式打字机必需） |

## 卡片 JSON 2.0 结构

```json
{
    "schema": "2.0",
    "header": {
        "title": {"content": "卡片标题", "tag": "plain_text"}
    },
    "body": {
        "elements": [
            {
                "tag": "markdown",
                "content": "卡片内容",
                "element_id": "markdown_1"
            }
        ]
    }
}
```

> `element_id` 为组件唯一标识，流式更新和局部操作时需要引用。需在卡片全局唯一。

## 发送卡片消息

### 方式一：直接发送卡片 JSON

```
POST /im/v1/messages?receive_id_type=chat_id
{
    "receive_id": "oc_xxx",
    "msg_type": "interactive",
    "content": "{\"schema\":\"2.0\",\"header\":{\"title\":{\"content\":\"标题\",\"tag\":\"plain_text\"}},\"body\":{\"elements\":[{\"tag\":\"markdown\",\"content\":\"内容\",\"element_id\":\"md_1\"}]}}"
}
```

### 方式二：发送卡片实体（支持流式）

先创建卡片实体，再通过 `card_id` 发送。**流式打字机必须用此方式。**

## 更新已发送的卡片

```
PATCH /im/v1/messages/{message_id}
{"content": "{更新的卡片JSON}"}
```

**限制**:
- 仅支持更新 `interactive` 类型消息
- 仅支持更新 14 天内发送的消息
- 单条消息更新频控 5 QPS
- 卡片前后均需显式声明 `"update_multi": true`（共享卡片，对所有接收者可见）

---

## 流式打字机效果

AI 场景下将 Agent 输出以打字机效果逐步渲染到卡片中。

**核心流程**: 创建卡片实体 → 发送卡片 → 流式更新文本 → 关闭流式模式

### 步骤一：创建卡片实体（开启流式模式）

```
POST /cardkit/v1/cards
{
    "type": "card_json",
    "data": "{\"schema\":\"2.0\",\"header\":{\"title\":{\"content\":\"AI回复\",\"tag\":\"plain_text\"}},\"config\":{\"streaming_mode\":true,\"summary\":{\"content\":\"\"},\"streaming_config\":{\"print_frequency_ms\":{\"default\":70},\"print_step\":{\"default\":1},\"print_strategy\":\"fast\"}},\"body\":{\"elements\":[{\"tag\":\"markdown\",\"content\":\"\",\"element_id\":\"md_1\"}]}}"
}
```

**响应**: `{"code":0, "data":{"card_id":"7371713483664506900"}}`

**流式配置字段**:

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `streaming_mode` | bool | false | 是否开启流式更新模式 |
| `streaming_config.print_frequency_ms` | object | 70 | 流式更新频率（ms），支持 default/android/ios/pc 分端配置 |
| `streaming_config.print_step` | object | 1 | 每次上屏增量字符数，支持分端配置 |
| `streaming_config.print_strategy` | enum | fast | `fast`：未上屏部分立即输出再开始本次；`delay`：未上屏部分继续打字机效果再开始本次 |

**权限**: `cardkit:card:write`

### 步骤二：发送卡片实体

```
POST /im/v1/messages?receive_id_type=chat_id
{
    "receive_id": "oc_xxx",
    "msg_type": "interactive",
    "content": "{\"type\":\"card\",\"data\":{\"card_id\":\"7371713483664506900\"}}"
}
```

**响应**: 返回 `message_id`（`om_xxx`）

**注意**:
- 卡片实体仅支持发送一次
- 发送应用必须是卡片实体的创建应用
- 发送后聊天栏消息预览显示 `[生成中...]`

### 步骤三：流式更新文本

```
PUT /cardkit/v1/cards/{card_id}/elements/{element_id}/content
{"content": "当前全量文本内容"}
```

- 传入**全量文本**，平台自动计算增量部分，以打字机效果逐字渲染
- 若旧文本是新文本的前缀子串，新增部分继续打字机效果
- 若新旧文本前缀不同，全量文本直接上屏，无打字机效果

**Agent 对接模式**:
```
Agent TEXT_DELTA 事件 → 累积全文 → 调用流式更新文本接口
```

**频率**: 单卡片卡片/组件级 OpenAPI 操作上限 10 次/秒

### 步骤四：关闭流式模式

文本输出完毕后，关闭流式模式以恢复正常卡片交互：

```
PUT /cardkit/v1/cards/{card_id}/settings
{"settings": "{\"config\":{\"streaming_mode\":false}}"}
```

**必须关闭的原因**:
- 流式模式下卡片无法被转发
- 流式模式下无法响应卡片交互回调
- 流式模式 10 分钟后自动关闭，建议手动关闭

### 流式打字机完整时序

```
Agent开始回复
    │
    ├─ 1. POST /cardkit/v1/cards (streaming_mode=true)
    │     → card_id
    │
    ├─ 2. POST /im/v1/messages (msg_type=interactive, card_id)
    │     → message_id
    │
    ├─ 3. Agent TEXT_DELTA 事件循环:
    │     PUT /cardkit/v1/cards/{card_id}/elements/{element_id}/content
    │     (传入累积全量文本，≤10次/秒)
    │
    └─ 4. Agent DONE 事件:
          PUT /cardkit/v1/cards/{card_id}/settings
          (streaming_mode=false)
```
