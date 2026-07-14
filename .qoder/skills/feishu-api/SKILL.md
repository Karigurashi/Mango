---
name: feishu-api
description: 飞书(Feishu/Lark)开放平台API集成技能。覆盖认证鉴权、消息收发、飞书卡片、流式打字机效果、表情反应、事件订阅等Channel通讯能力。当需要将Agent接入飞书机器人、实现飞书消息通道、或进行飞书机器人开发时使用。
---

# 飞书 Channel 通讯集成

## 架构定位：两层分工

| 层 | 职责 | 技术 | 本 Skill 覆盖 |
|---|---|---|---|
| **消息通道层** | 收消息→Agent→发回复、卡片流式输出、表情反应 | 飞书 OpenAPI + lark-oapi SDK | ✅ 本 skill |
| **飞书操作层** | Agent 主动操作飞书（多维表格、云文档、日历、通讯录、审批等） | 官方 lark-openapi-mcp（MCP Server） | ❌ MCP 负责 |

> 飞书全量 OpenAPI 操作能力由官方 MCP Server (`@larksuiteoapi/lark-mcp`) 提供，本 skill 仅覆盖 **Channel 管道层**所需的通讯 API。

## 基础信息

- **API 基础域名**: `https://open.feishu.cn/open-apis`
- **国际版域名**: `https://open.larksuite.com/open-apis`
- **请求头**: `Authorization: Bearer {access_token}`, `Content-Type: application/json; charset=utf-8`
- **响应格式**: `{"code": 0, "msg": "success", "data": {...}}`，非 0 表示失败

## 认证

Channel 自身调用飞书 API 使用 `tenant_access_token`（应用身份）：

```
POST /auth/v3/tenant_access_token/internal
{"app_id": "cli_xxx", "app_secret": "xxx"}
→ {"code":0, "tenant_access_token":"t-xxx", "expire":7200}
```

有效期 2 小时。App ID / App Secret 在开发者后台 > 基础信息 > 凭证与基础信息获取。

## Channel 核心能力

| 能力 | 核心接口 | 参考文档 |
|---|---|---|
| **消息通讯** | 收消息(WebSocket)、发消息、回复、上传图片文件 | [reference/messaging.md](reference/messaging.md) |
| **飞书卡片** | 发送卡片、更新卡片、流式打字机效果 | [reference/card.md](reference/card.md) |
| **表情反应** | 添加/删除消息表情 | [reference/messaging.md](reference/messaging.md) |
| **事件订阅** | WebSocket 长连接、Webhook 回调、事件类型 | [reference/events.md](reference/events.md) |

## 消息类型速查

发送消息 `POST /im/v1/messages?receive_id_type={open_id|user_id|union_id|email|chat_id}`：

| msg_type | content 示例 | 用途 |
|---|---|---|
| `text` | `{"text":"消息内容"}` | 纯文本 |
| `post` | `{"zh_cn":{"title":"标题","content":[[{"tag":"text","text":"段落"}]]}}` | 富文本 |
| `image` | `{"image_key":"img_v2_xxx"}` | 图片 |
| `interactive` | 卡片 JSON 或 `{"type":"card","data":{"card_id":"xxx"}}` | 飞书卡片 |

限频: 同一用户 5 QPS，同一群组 5 QPS。响应返回 `message_id`（`om_xxx`）。

## Channel 权限

| 权限标识 | 说明 |
|---|---|
| `im:message` / `im:message:send_as_bot` | 发送消息 |
| `im:message.p2p_msg:readonly` | 读取单聊消息 |
| `im:message.group_at_msg:readonly` | 读取群@机器人消息 |
| `im:message.reactions:write_only` | 发送、删除消息表情回复 |
| `im:resource` | 上传/下载图片文件 |
| `cardkit:card:write` | 创建与更新卡片（流式打字机必需） |

## 参考资源

- 开放平台文档: https://open.feishu.cn/document
- API 调试台: https://open.feishu.cn/api-explorer
- Python SDK: `pip install lark-oapi`
- 卡片搭建工具: https://open.feishu.cn/cardkit
- 官方 MCP Server: `npx @larksuiteoapi/lark-mcp`
---
name: feishu-api
description: 飞书(Feishu/Lark)开放平台API集成技能。覆盖认证鉴权、消息收发、群组管理、多维表格读写、云文档操作、日历日程、通讯录、审批等全量API。当需要将Agent接入飞书、读写飞书消息/文档/表格/日历/通讯录、或进行飞书机器人开发时使用。
---

# 飞书开放平台 API 集成

## 基础信息

- **API 基础域名**: `https://open.feishu.cn/open-apis`
- **国际版域名**: `https://open.larksuite.com/open-apis`
- **请求头**: `Authorization: Bearer {access_token}`, `Content-Type: application/json; charset=utf-8`
- **响应格式**: `{"code": 0, "msg": "success", "data": {...}}`，非 0 表示失败

## 认证鉴权

| Token | 前缀 | 场景 | 需用户授权 |
|---|---|---|---|
| `tenant_access_token` | `t-` | 应用身份自动化操作（机器人发消息等） | 否 |
| `user_access_token` | `u-` | 代理用户操作（创建用户文档等） | 是 |

**获取 tenant_access_token（最常用）**:

```
POST /auth/v3/tenant_access_token/internal
{"app_id": "cli_xxx", "app_secret": "xxx"}
→ {"code":0, "tenant_access_token":"t-xxx", "expire":7200}
```

有效期 2 小时。App ID / App Secret 在开发者后台 > 基础信息 > 凭证与基础信息获取。

> 完整认证流程（user_access_token、刷新机制等）见 [reference/auth.md](reference/auth.md)

## API 领域路由

按需查阅对应领域的完整 API 参考：

| 领域 | 核心能力 | 参考文档 |
|---|---|---|
| 消息（IM） | 发送/回复/撤回消息、上传图片文件、接收消息事件 | [reference/im.md](reference/im.md) |
| 群组管理 | 创建/解散群、群成员管理、管理员设置 | [reference/im.md](reference/im.md) |
| 多维表格 | 记录CRUD、字段管理、查询过滤排序 | [reference/bitable.md](reference/bitable.md) |
| 云文档 | 文档/云空间/知识库/电子表格 | [reference/docs.md](reference/docs.md) |
| 日历 | 日程CRUD、参与人管理、忙闲查询 | [reference/calendar.md](reference/calendar.md) |
| 通讯录 | 用户/部门/用户组/角色管理 | [reference/contact.md](reference/contact.md) |
| 审批 | 审批定义/实例/任务操作 | [reference/approval.md](reference/approval.md) |
| 事件订阅 | WebSocket/Webhook接入、事件类型、事件加密 | [reference/events.md](reference/events.md) |

## 消息类型速查

发送消息 `POST /im/v1/messages?receive_id_type={open_id|user_id|union_id|email|chat_id}`：

| msg_type | content 示例 |
|---|---|
| `text` | `{"text":"消息内容"}` |
| `post` | `{"zh_cn":{"title":"标题","content":[[{"tag":"text","text":"段落"}]]}}` |
| `image` | `{"image_key":"img_v2_xxx"}` |
| `file` | `{"file_key":"file_v2_xxx"}` |
| `media` | `{"file_key":"file_v2_xxx","image_key":"img_v2_xxx"}` |
| `interactive` | 卡片 JSON 结构 |

限频: 同一用户 5 QPS，同一群组 5 QPS。响应返回 `message_id`（`om_xxx`）。

> 完整消息 API（回复、历史、撤回、上传下载等）见 [reference/im.md](reference/im.md)

## 接入前提

1. **创建应用**: https://open.feishu.cn/app 创建企业自建应用
2. **开启机器人能力**: 应用功能 > 机器人
3. **配置权限**: 权限管理页面申请所需 API 权限
4. **配置事件订阅**: 添加事件类型，配置回调地址或使用长连接
5. **发布应用**: 创建版本并发布，权限才生效
6. **可用范围**: 设置应用可用范围（全体员工或指定部门/用户）

### 核心权限速查

| 权限标识 | 说明 |
|---|---|
| `im:message` / `im:message:send_as_bot` | 发送消息 |
| `im:message.p2p_msg:readonly` | 读取单聊消息 |
| `im:message.group_at_msg:readonly` | 读取群@机器人消息 |
| `im:chat` / `im:chat:write` | 群组管理 |
| `im:resource` | 上传/下载图片文件 |
| `bitable:app` / `bitable:app:readonly` | 多维表格读写 |
| `docx:document` / `docx:document:readonly` | 文档读写 |
| `drive:drive` / `drive:drive:readonly` | 云空间文件 |
| `calendar:calendar` / `calendar:calendar:readonly` | 日历日程 |
| `contact:contact.base:readonly` | 通讯录读取 |
| `approval:approval` | 审批管理 |

> 各领域完整权限列表见对应 reference 文件的「权限」章节

## 参考资源

- 开放平台文档: https://open.feishu.cn/document
- API 调试台: https://open.feishu.cn/api-explorer
- Python SDK: `pip install lark-oapi`
- 卡片搭建工具: https://open.feishu.cn/cardkit
