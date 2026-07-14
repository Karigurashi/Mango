# 消息通讯与表情反应

## 权限

| 权限标识 | 说明 |
|---|---|
| `im:message` / `im:message:send_as_bot` | 发送消息 |
| `im:message.p2p_msg:readonly` | 读取单聊消息 |
| `im:message.group_at_msg:readonly` | 读取群@机器人消息 |
| `im:message.reactions:write_only` | 发送、删除消息表情回复 |
| `im:resource` | 上传/下载图片和文件 |

## 发送消息

| 项目 | 值 |
|---|---|
| **URL** | `POST /im/v1/messages` |
| **Token** | `tenant_access_token` 或 `user_access_token` |
| **频率** | 1000次/分钟, 50次/秒；同一用户/群组 5 QPS |

**查询参数**: `receive_id_type` = `open_id`/`union_id`/`user_id`/`email`/`chat_id`

**请求体**:

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `receive_id` | string | 是 | 接收者 ID |
| `msg_type` | string | 是 | `text`/`post`/`image`/`file`/`audio`/`media`/`sticker`/`interactive`/`share_chat`/`share_user` |
| `content` | string | 是 | JSON 序列化字符串，与 msg_type 对应 |
| `uuid` | string | 否 | 去重 ID，相同 uuid 1小时内至多成功发送一条 |

**响应**: `{"code":0, "data":{"message_id":"om_xxx", "chat_id":"oc_xxx", ...}}`

## 回复消息

```
POST /im/v1/messages/{message_id}/reply
{"msg_type":"text", "content":"{\"text\":\"回复内容\"}"}
```

## 获取历史消息

```
GET /im/v1/messages?container_id_type=chat&container_id={chat_id}&start_time={ts}&end_time={ts}&page_size=50
```

## 获取单条消息

```
GET /im/v1/messages/{message_id}
```

## 撤回消息

```
DELETE /im/v1/messages/{message_id}
```

## 更新消息

```
PATCH /im/v1/messages/{message_id}
```

> 更新消息卡片内容详见 [card.md](card.md)

## 上传图片

| 项目 | 值 |
|---|---|
| **URL** | `POST /im/v1/images` |
| **Content-Type** | `multipart/form-data` |
| **格式** | JPEG/PNG/WEBP/GIF/TIFF/BMP/ICO |
| **大小** | 建议 5MB 内 |

**表单参数**: `image_type=message`, `image=<binary>`

**响应**: `{"image_key": "img_v2_xxx"}`

## 下载图片

```
GET /im/v1/images/{image_key}
```

## 上传文件

| 项目 | 值 |
|---|---|
| **URL** | `POST /im/v1/files` |
| **Content-Type** | `multipart/form-data` |
| **大小** | ≤30MB |

**表单参数**: `file_type`(ppt/pdf/doc/xls/mp4/mp3/...), `file_name`, `file=<binary>`

**响应**: `{"file_key": "file_v2_xxx"}`

## 下载文件

```
GET /im/v1/files/{file_key}
```

---

## 表情反应

### 添加表情回复

```
POST /im/v1/messages/{message_id}/reactions
```

**请求体**:
```json
{"reaction_type": {"emoji_type": "SMILE"}}
```

**响应**:
```json
{
    "code": 0, "msg": "success",
    "data": {
        "reaction_id": "ZCaCIjUBVVWSrm5L-3ZTw****",
        "operator": {"operator_id": "ou_xxx", "operator_type": "user"},
        "action_time": "1663054162546",
        "reaction_type": {"emoji_type": "SMILE"}
    }
}
```

**权限**: `im:message` 或 `im:message.reactions:write_only`

**频率**: 1000次/分钟, 50次/秒

**限制**:
- 已撤回的消息无法添加表情
- 系统消息（system）无法添加表情
- 机器人需在消息所属会话内

### 删除表情回复

```
DELETE /im/v1/messages/{message_id}/reactions/{reaction_id}
```

### 获取表情回复列表

```
GET /im/v1/messages/{message_id}/reactions?reaction_type={emoji_type}
```

### 常用 emoji_type

| emoji_type | 表情 | emoji_type | 表情 |
|---|---|---|---|
| `SMILE` | 😊 | `THUMBSUP` | 👍 |
| `HEART` | ❤️ | `OK` | 👌 |
| `YES` | ✅ | `NO` | ❌ |
| `CRY` | 😢 | `LAUGH` | 😄 |

> 完整列表见飞书文档: https://open.feishu.cn/document/emojis-introduce
