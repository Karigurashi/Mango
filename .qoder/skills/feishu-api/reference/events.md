# 事件订阅

## 订阅方式

| 方式 | 说明 | 适用 |
|---|---|---|
| **WebSocket 长连接** | SDK 内建，无需公网服务器 | 本地开发、快速接入（推荐） |
| **Webhook 回调** | 提供公网 URL 接收 POST | 生产环境 |

## Python SDK 长连接

```python
import lark_oapi as lark

def do_p2_im_message_receive_v1(data):
    print(f'收到消息: {data}')

event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()

cli = lark.ws.Client("APP_ID", "APP_SECRET", event_handler=event_handler)
cli.start()
```

**Channel 对接模式**:
```python
# 在事件回调中转为 ChannelMessage 并投递给 Channel
def do_p2_im_message_receive_v1(data):
    msg = data.event.message
    sender = data.event.sender
    channel_msg = ChannelMessage(
        groupId=msg.chat_id,
        userId=sender.sender_id.open_id,
        content=extract_text(msg),
        userName=sender.sender_id.open_id,
    )
    asyncio.create_task(channel.ReceiveMessageAsync(channel_msg))
```

## Python SDK Webhook（Flask）

```python
from flask import Flask
from lark_oapi.adapter.flask import *
import lark_oapi as lark

app = Flask(__name__)
event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(lambda data: print(data)) \
    .build()

@app.route("/webhook/event", methods=["POST"])
def event():
    return parse_resp(event_handler.do(parse_req()))

app.run(port=7777)
```

**Webhook 首次验证**: 飞书发送 `{"challenge":"xxx","type":"url_verification"}`，需原样返回 `{"challenge":"xxx"}`。

## Channel 常用事件类型

| 事件类型 | 说明 | 权限 |
|---|---|---|
| `im.message.receive_v1` | 接收消息 | `im:message.p2p_msg:readonly` 或 `im:message.group_at_msg:readonly` |
| `im.message.message_read_v1` | 消息已读 | `im:message` |
| `im.chat.member.bot.added_v1` | 机器人进群 | `im:chat` |
| `im.chat.member.bot.deleted_v1` | 机器人被移出群 | `im:chat` |
| `im.message.reaction.created_v1` | 表情回复新增 | `im:message` |
| `im.message.reaction.deleted_v1` | 表情回复删除 | `im:message` |

## 接收消息事件体

事件类型 `im.message.receive_v1`：

```json
{
    "schema": "2.0",
    "header": {
        "event_id": "唯一事件ID",
        "event_type": "im.message.receive_v1",
        "create_time": "毫秒时间戳",
        "token": "verification_token",
        "app_id": "cli_xxx",
        "tenant_key": "租户标识"
    },
    "event": {
        "sender": {
            "sender_id": {"open_id": "ou_xxx"},
            "sender_type": "user"
        },
        "message": {
            "message_id": "om_xxx",
            "chat_id": "oc_xxx",
            "chat_type": "group",
            "message_type": "text",
            "content": "{\"text\":\"@_user_1 hello\"}",
            "mentions": [
                {"key": "@_user_1", "id": {"open_id": "ou_xxx"}, "name": "Tom"}
            ]
        }
    }
}
```

**关键字段**:
- `chat_type`: `p2p`（单聊）/ `group`（群聊）
- `message_id`: 用于去重和回复
- `mentions`: @机器人信息，`key` 用于替换 content 中的占位符

## Webhook URL 验证

首次配置 Webhook 时，飞书发送:
```json
{"challenge": "xxx", "token": "xxx", "type": "url_verification"}
```
需原样返回: `{"challenge": "xxx"}`

## 事件加密

若配置了 Encrypt Key:
- 事件体为: `{"encrypt": "加密Base64内容"}`
- 解密: AES-256-CBC，key = SHA256(Encrypt Key) 前32字节，iv = 密文前16字节
# 事件订阅

## 订阅方式

| 方式 | 说明 | 适用 |
|---|---|---|
| **WebSocket 长连接** | SDK 内建，无需公网服务器 | 本地开发、快速接入（推荐） |
| **Webhook 回调** | 提供公网 URL 接收 POST | 生产环境 |

## Python SDK 长连接

```python
import lark_oapi as lark

def do_p2_im_message_receive_v1(data):
    print(f'收到消息: {data}')

event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
    .build()

cli = lark.ws.Client("APP_ID", "APP_SECRET", event_handler=event_handler)
cli.start()
```

## Python SDK Webhook（Flask）

```python
from flask import Flask
from lark_oapi.adapter.flask import *
import lark_oapi as lark

app = Flask(__name__)
event_handler = lark.EventDispatcherHandler.builder("", "") \
    .register_p2_im_message_receive_v1(lambda data: print(data)) \
    .build()

@app.route("/webhook/event", methods=["POST"])
def event():
    return parse_resp(event_handler.do(parse_req()))

app.run(port=7777)
```

**Webhook 首次验证**: 飞书发送 `{"challenge":"xxx","type":"url_verification"}`，需原样返回 `{"challenge":"xxx"}`。

## 常用事件类型

| 事件类型 | 说明 | 权限 |
|---|---|---|
| `im.message.receive_v1` | 接收消息 | `im:message.p2p_msg:readonly` 或 `im:message.group_at_msg:readonly` |
| `im.message.message_read_v1` | 消息已读 | `im:message` |
| `im.chat.member.bot.added_v1` | 机器人进群 | `im:chat` |
| `im.chat.member.bot.deleted_v1` | 机器人被移出群 | `im:chat` |
| `contact.user.created_v3` | 员工入职 | `contact:contact.base:readonly` |
| `contact.user.updated_v3` | 员工信息变更 | `contact:contact.base:readonly` |
| `contact.user.deleted_v3` | 员工离职 | `contact:contact.base:readonly` |
| `contact.department.created_v3` | 部门创建 | `contact:contact.base:readonly` |
| `contact.department.updated_v3` | 部门变更 | `contact:contact.base:readonly` |
| `calendar.calendar.event.changed_v4` | 日程变更 | `calendar:calendar:readonly` |

## 接收消息事件体

事件类型 `im.message.receive_v1`，事件体关键字段:

```json
{
    "header": {"event_type": "im.message.receive_v1", "tenant_key": "xxx"},
    "event": {
        "sender": {"sender_id": {"open_id": "ou_xxx"}, "sender_type": "user"},
        "message": {
            "message_id": "om_xxx",
            "chat_id": "oc_xxx",
            "chat_type": "group",
            "message_type": "text",
            "content": "{\"text\":\"@_user_1 hello\"}",
            "mentions": [{"key":"@_user_1", "id":{"open_id":"ou_xxx"}, "name":"Tom"}]
        }
    }
}
```

用 `message_id` 去重。`chat_type` 区分单聊(p2p)/群聊(group)。

## 事件体统一格式（schema 2.0）

```json
{
    "schema": "2.0",
    "header": {
        "event_id": "唯一事件ID",
        "event_type": "事件类型",
        "create_time": "毫秒时间戳",
        "token": "verification_token",
        "app_id": "cli_xxx",
        "tenant_key": "租户标识"
    },
    "event": { ... }
}
```

## Webhook URL 验证

首次配置 Webhook 时，飞书发送:
```json
{"challenge": "xxx", "token": "xxx", "type": "url_verification"}
```
需原样返回: `{"challenge": "xxx"}`

## 事件加密

若配置了 Encrypt Key:
- 事件体为: `{"encrypt": "加密Base64内容"}`
- 解密: AES-256-CBC，key = SHA256(Encrypt Key) 前32字节，iv = 密文前16字节
