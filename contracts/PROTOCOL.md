# AIChat 统一接口规约 v1

本文是实施阶段的**唯一权威契约**，锁定后端 `services/server`、连接器 `connectors/connector-runner`、移动端 `apps/mobile` 三方共同遵守的接口。与设计文档冲突时以本文为准；修改本文必须同步三方实现。

依据：`项目最终架构.md`（模块划分、技术栈：Python+FastAPI+PostgreSQL）、`docs/AI接入协议.md`（配对与运行协议）、`docs/产品需求.md`（功能范围）。

## 0. 通用约定

- REST 前缀 `/v1`，Content-Type `application/json`。
- ID 为不透明字符串（UUID hex）；时间为 UTC RFC3339；`seq`/`cursor`/`revision` 等大数一律**十进制字符串**序列化。
- 成功响应：`{"request_id": "...", "data": {...}}`；错误响应：`{"request_id": "...", "error": {"code": "...", "message": "...", "retryable": bool, "retry_after_ms": int?}}`。
- 人类认证：`Authorization: Bearer <access_token>`（audience=human）。连接器认证：audience=connector。两者票据不可互换。
- 请求中的身份字段（sender_id / owner_id 等）一律忽略或拒绝，作者身份从认证推导。
- 未知枚举值必须拒绝；未知可选字段可忽略。

### 错误码

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | VALIDATION_FAILED | 字段/mentions 不合法 |
| 400 | VERSION_UNSUPPORTED | 协议版本不兼容 |
| 401 | AUTH_INVALID | 凭据缺失/无效/过期 |
| 401 | SESSION_REVOKED | 会话或凭据已撤销 |
| 403 | FORBIDDEN | 权限不足 |
| 403 | MEMBERSHIP_REVOKED | 成员身份已失效 |
| 404 | NOT_FOUND | 不存在或需隐藏存在 |
| 409 | IDEMPOTENCY_CONFLICT | 同幂等键不同内容 |
| 409 | VERSION_CONFLICT | expected_version 不匹配 |
| 410 | CURSOR_EXPIRED | 事件游标过期，需 resync |
| 422 | CAPABILITY_UNSUPPORTED | 能力不支持 |
| 429 | RATE_LIMITED / SLOW_DOWN | 限流，按 retry_after_ms 退避 |
| 503 | TEMPORARILY_UNAVAILABLE | 短暂不可用，可幂等重试 |
| 400 | PAIRING_PENDING | 配对仍在等待 |
| 400 | PAIRING_DENIED / PAIRING_EXPIRED / PAIRING_REVOKED / PAIRING_CONSUMED | 配对终态/已消费 |
| 400 | CONTEXT_TOO_LARGE | 上下文超限且无法保留触发消息 |
| 409 | STALE_FENCE | fencing token / attempt 过期 |
| 409 | DELTA_GAP | delta 缺片 |

### 数值默认（可配置）

| 参数 | 默认值 |
| --- | --- |
| 配对有效期 / 轮询间隔 | 5 分钟 / 5 秒 |
| 短码 user_code | 8 位易读字符；确认码 confirm_code 6 位数字 |
| device_code | 256 bit 随机，仅创建时返回，服务端只存哈希 |
| 连接器访问令牌 / 刷新凭据 | 15 分钟 / 7 天 |
| WSS 票据 | 30 秒一次性，连接后首帧提交 |
| 心跳 / 离线判定 | 20 秒 / 60 秒 |
| 运行租约 / 续租 | 30 秒 / 每 10 秒 |
| 聊天 deadline / 离线排队上限 | 120 秒 / 5 分钟 |
| 未开工领取次数上限 | 3 次，超过转 failed |
| 事件保留 / AI 消息上限 / 人类消息上限 | 7 天 / 256 KiB / 16 KiB |
| 上下文条数 / 每 AI 并发 / 每人并发 / 每 AI 队列 | 30 条 / 1 / 2 / 20 |
| 单条群消息 @ AI 上限 | 3 |

## 1. 认证与账号（identity）

| 接口 | 请求 | 成功 data |
| --- | --- | --- |
| POST /v1/auth/register | invite_code、handle、display_name、password | account |
| POST /v1/auth/login | handle、password、device_summary? | access_token、refresh_token、expires_in、account |
| POST /v1/auth/refresh | refresh_token | 同 login（刷新凭据轮换，旧 token 失效） |
| POST /v1/auth/logout | Bearer | revoked: true |
| GET /v1/me | Bearer | account |
| POST /v1/realtime-tickets | Bearer；audience=human_events 或 connector | ticket、expires_in |

account 对象：`{account_id, kind: "human"|"ai", handle, display_name, avatar_url?, bio?, status}`。

注册走邀请码；首个管理员由 bootstrap CLI 创建。密码 argon2id。

## 2. 联系人（contacts）

| 接口 | 说明 |
| --- | --- |
| GET /v1/accounts/by-handle?handle= | 精确查找，返回有限资料 |
| POST /v1/contact-requests | {target_account_id}；AI 目标由其所有者审批 |
| POST /v1/contact-requests/{id}/decision | {decision: accept/reject} |
| GET /v1/contacts | items: account + 关系 |
| DELETE /v1/contacts/{account_id} | 移除联系人（阻止新私聊，历史保留） |
| POST /v1/contacts/{account_id}/block | 拉黑（方向性） |

规则：无序账号对唯一联系人关系；所有者对自己的 AI 自动接受并建立使用授权。

## 3. 会话与成员（conversations）

| 接口 | 说明 |
| --- | --- |
| POST /v1/conversations/direct | {target_account_id, client_request_id}；幂等，已存在返回原会话 |
| POST /v1/groups | {title, member_account_ids[]}；创建者为群主，其余发邀请 |
| POST /v1/conversations/{id}/invitations | 群主/管理员邀请；邀请 AI 需其所有者确认（AI 邀请的被邀方=所有者） |
| POST /v1/invitations/{id}/decision | 被邀人/AI 所有者 accept/reject |
| DELETE /v1/conversations/{id}/members/{membership_id} | 移除成员或本人退出；群主先转让或解散 |
| DELETE /v1/conversations/{id} | 群主解散 |
| GET /v1/conversations | 列表 + 最后消息摘要 + 未读 |
| GET /v1/conversations/{id} | 详情 + 当前成员/角色 |

membership 对象：`{membership_id, conversation_id, account_id, role: member|admin|owner, joined_seq, left_seq?}`。
成员区间：`joined_seq ≤ seq ≤ (left_seq 或 ∞)` 决定历史可见性；重新加入形成新区间。成员变更递增 conversation.permission_version 并发系统消息。

## 4. 消息（messages）

| 接口 | 说明 |
| --- | --- |
| POST /v1/conversations/{id}/messages | {client_message_id, text, mentions[]?, reply_to_message_id?} → 201/200 幂等：`{message, runs[]}` |
| GET /v1/conversations/{id}/messages?before_seq=&limit= | 按 seq 升序分页，仅返回可见区间 |
| PUT /v1/conversations/{id}/read | {through_seq} 只前进 |

message 对象：`{message_id, conversation_id, seq, sender_account_id, kind: "text"|"system", text, mentions, client_message_id?, reply_to_message_id?, run_id?, trigger_message_id?, status: "draft"|"partial"|"final", terminal_reason?, revision, created_at, updated_at}`。

规则：
- 幂等键 `conversation_id + sender + client_message_id`；同键不同内容 409。
- mentions 必须是当前成员账号 ID；引用必须同会话且可见。
- 人类→AI 私聊消息自动触发 Run；群聊仅显式 @ AI 触发（≤3 个）；AI 输出不触发其他 AI。
- AI 回复消息在 run.started 时以 draft 占位创建，delta 检查点更新为 partial，终态 final。

## 5. 事件与实时（realtime）

### 5.1 HTTP 补拉

`GET /v1/events?after=<cursor>&limit=` → `{items: [{event_id, cursor, type, conversation_id?, seq?, payload, occurred_at}], next_cursor, has_more}`。cursor 过期返回 410 CURSOR_EXPIRED，客户端全量 resync。

持久事件类型：`message.created`、`message.updated`、`membership.changed`、`conversation.closed`、`run.updated`、`binding.changed`。
临时事件（仅 WSS）：`run.delta`、`typing`、`presence`。

### 5.2 人类 WSS `/v1/realtime`

1. 连接后 10 秒内首帧提交票据：`{"type":"ticket","ticket":"..."}`；失败即关闭。
2. 服务端回 `{"type":"welcome","current_cursor":"..","heartbeat_seconds":20}`，随后推送 welcome 之后该账号的全部持久事件与实时事件。
3. 持久事件帧：`{"protocol_version":1,"type":"message.created","event_id":"..","cursor":"..","conversation_id":"..","seq":"..","payload":{...},"occurred_at":".."}`。
4. 客户端可发 `{"type":"ping"}`，服务端回 `{"type":"pong"}`；60 秒无帧判离线。
5. 事件按 event_id 去重、按 cursor 单调应用；消息渲染以 HTTP 快照 + revision 合并为准。

## 6. AI 与绑定（agents）

| 接口 | 说明 |
| --- | --- |
| POST /v1/agents | {display_name, handle, bio?} 创建 AI 账号+档案（unbound） |
| GET /v1/agents?scope=owned / GET /v1/agents/{id} | 档案 + 绑定状态 + 在线状态 |
| PATCH /v1/agents/{id} | {display_name?/status?} |
| POST /v1/agents/{id}/model-binding | {provider_code, credential(secret), model_name, system_prompt?}；服务端加密保存，测试通过启用 |
| POST /v1/agents/{id}/binding/revoke | 撤销绑定，generation+1，取消在途运行 |
| POST /v1/agents/{id}/grants | {human_account_id} 授权使用 / DELETE 撤销 |
| GET /v1/agents/{id}/connectors | 所有者查看已绑定连接器 |

供应商端点白名单由管理员维护（表 provider_endpoint），协议 openai_chat（OpenAI 兼容 chat/completions）。

## 7. 配对与连接器（pairing）

状态机：`pending_user → pending_local → approved → redeemed`；非终态可转 `denied / expired / cancelled`。

| 接口 | 主体 | 请求/响应 |
| --- | --- | --- |
| POST /v1/pairings | 匿名 | req: {agent_id, connector_name, platform, adapter_kind, requested_capabilities[]} → 201: {pairing_id, short_code, qr_payload, confirm_code, device_code, expires_at, interval_seconds} |
| GET /v1/pairings/{id} | 已登录人类 + ?code=short_code | {pairing_id, agent_id, agent_display_name, owner_account_id, connector_name, platform, requested_capabilities, confirm_code, status, version, expires_at} |
| POST /v1/pairings/{id}/decision | AI 所有者 | {decision: approve/deny, confirm_code, expected_version} → approve 后状态 pending_local |
| POST /v1/pairing-status | 连接器（device_code） | {device_code} → {status}；pending_local 时附 {owner_display_name, agent_display_name, confirm_code} 供本机核对 |
| POST /v1/pairing-local-confirmation | 连接器 | {device_code, confirmed: true} → approved |
| POST /v1/pairing-token | 连接器 | {device_code} 一次性兑换 → {connector_id, agent_id, access_token, refresh_credential, expires_in}；重复兑换 409 PAIRING_CONSUMED |
| POST /v1/connectors/access-tokens | 连接器 | {refresh_credential} → {access_token, expires_in} |
| POST /v1/connectors/{id}/revoke | AI 所有者 | 撤销连接器，关闭会话，generation+1 |

qr_payload 形如 `https://<host>/pair?pid=<pairing_id>&code=<short_code>`，不含任何秘密。device_code 仅创建响应出现一次。兑换成功：创建 connector 记录、RuntimeBinding(mode=connector, generation+1)、撤销该 AI 旧连接器与在途运行。

### 连接器 WSS `/v1/connectors/realtime`

1. 先用访问令牌换票据（POST /v1/realtime-tickets, audience=connector），连接后首帧 `{"type":"ticket","ticket":"..."}`。
2. C→S `connector.hello` `{protocol_version:1, connector_id, adapter_kind, adapter_version?, capabilities:["chat.text","output.stream","run.cancel","run.query"]}`
3. S→C `connector.welcome` `{protocol_version, heartbeat_seconds, lease_seconds, effective_capabilities}`
4. C→S `connector.ready` / `connector.degraded` `{reason?}` 上报 Agent 实际可用性（配对成功≠模型可用）。
5. 心跳：任一方 20 秒发 `{"type":"heartbeat"}`；60 秒无帧判离线。
6. 运行控制帧（公共字段：run_id、execution_id、attempt_no、fencing_token；服务端帧另有 event_id、occurred_at）：

| type | 方向 | payload 附加字段 |
| --- | --- | --- |
| run.offer | S→C | binding_generation, lease_until, agent_id, conversation_id, trigger_message_id, context:[{seq, sender_account_id, sender_kind, text, truncated}], system_prompt?, policy:{deadline_at, max_output_bytes} |
| run.accepted | C→S | （仅公共字段；10 秒内未 ack 可回收重派） |
| run.started | C→S | （服务端据此创建 draft 回复消息、置 running） |
| run.delta | C→S | chunk_index, text |
| run.completed | C→S | final_text（≤32KiB）或 content_hash（持久聚合文本 SHA-256）、last_chunk_index、usage?、finish_reason |
| run.failed | C→S | error_code, message(脱敏), side_effect_status: none/confirmed/unknown |
| run.cancel | S→C | reason |
| run.cancelled | C→S | side_effect_status |
| run.query | C→S | execution_id（重连时查询既有执行） |
| run.status | S→C | state, attempt_no, fencing_token, may_continue |

连接器必须按 execution_id 在本地账本持久去重；断线重连先 run.query 附着原执行，不新建。旧 fencing_token 提交返回 409 STALE_FENCE 帧。delta 重复同序号同内容幂等，不同内容 IDEMPOTENCY_CONFLICT；缺片返回 DELTA_GAP + next_chunk_index。

## 8. 运行（runs）

Run 状态：`queued → dispatched → running → succeeded`；终态 `failed / cancelled / expired`；`cancel_requested` 取消中；`recovery_required` 结果未知需人工处理。

| 接口 | 说明 |
| --- | --- |
| GET /v1/runs/{id} | 触发者/所有者/可见成员查看脱敏状态 |
| POST /v1/runs/{id}/cancel | 202 cancel_requested；尽力取消 |
| POST /v1/runs/{id}/retry | 新建 Run（显式重试），指向原运行 |

模型 API 模式由后端 worker 直接执行（OpenAI 兼容流式）；连接器模式经连接器网关派发。两者产出同一种 Run/Message/事件。

## 9. 后端模块接口规则（services/server 内部）

模块 = `aichat/modules/<name>/`，统一包含：`models.py`（表）、`schemas.py`（Pydantic DTO）、`service.py`（业务逻辑，**唯一跨模块入口**）、`router.py`（HTTP，仅 app 装配引用）。

- 跨模块调用只允许 `OtherService` 的公开方法；禁止 import 其他模块的 models/router 内部。
- 异步集成一律经 outbox 事件（`core/outbox.py`）事务内写入，由分发器扇出为 per-account inbox 事件再实时推送。
- 统一锁序：conversation → run → attempt → message；配对独立：agent → pairing → connector。
- 所有外部 I/O（模型调用、连接器通信）不得发生在持有数据库事务时。
- 时间/序号由服务端分配；客户端时间仅作展示。

## 10. 目录归属

```text
apps/mobile/                uni-app + Vue3 + TS 客户端
services/server/            FastAPI 模块化单体 + worker
connectors/connector-runner/  Python 连接器（配对客户端 + 执行运行层）
contracts/                  本规约 + 生成的 OpenAPI/JSON Schema
tests/                      跨模块集成测试
deploy/                     docker-compose 等非秘密部署模板
```
