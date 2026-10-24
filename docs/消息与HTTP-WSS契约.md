# 消息与 HTTP-WSS 契约

## 版本、对象与共用约定

本文是 human 客户端 REST/WSS 与消息语义的权威契约，均为待实现设计；配对与 runner 控制见[统一 AI 接入](统一AI接入.md)。
REST 前缀 `/v1`，JSON Content-Type；WSS envelope 的 v 固定 `aichat.v1`，不兼容变更升级主版本。
同版本只增可选字段，未知可选字段可忽略；未知命令、未知枚举及冒充身份字段必须拒绝。
ID 是不透明字符串，时间为 UTC RFC3339，seq/cursor/revision 为十进制字符串，避免跨端大整数精度丢失。
示例使用可读虚构 ID，不是实际已分配对象；本文没有已运行 API。

| 对象 | 含义 | 权威性 |
| --- | --- | --- |
| message | 会话中的持久业务消息，含文本与发送者 | 数据库权威，以 message_id 和 conversation seq 定位 |
| delta | AI 输出的一段增量 | 非独立业务消息，不能代替最终快照 |
| run / attempt | 一次 AI 任务 / 某次领取执行 | 不等于聊天消息或事件 |
| tool approval/status | 工具操作审批及状态 | 绑定具体 attempt 和参数摘要，不当作 AI 发言 |
| event | 状态变化的传递封装 | 可重复、可过期，消费者需去重与恢复 |
| audit_event | 敏感操作摘要 | 不向普通会话广播，不作为消息历史 |

human 请求使用 audience=human 的 bearer token，subject 为 account_id；具体登录凭据方式 D1 确定。
服务端拒绝请求中的 sender_id/sender_account_id/owner_id 等可伪造身份字段；从 session 或 runner 绑定推导。
默认请求超时 15 秒；超时不代表服务器未提交，发送重试必须沿用原 client_message_id。

## 公共 REST 成功与错误

成功响应含 request_id、data；错误含 request_id、error.code、error.message、error.retryable、可选 retry_after_ms。
message 为安全摘要，不返回内部栈、凭据、未授权对象的详细信息。

```json
{"request_id":"req-example","error":{"code":"IDEMPOTENCY_CONFLICT","message":"相同发送标识对应不同内容","retryable":false}}
```

| HTTP / code | 场景 | 客户端动作 |
| --- | --- | --- |
| 400 VALIDATION_FAILED / VERSION_UNSUPPORTED | 字段、mentions 或版本不合法 | 修正后新请求，不盲目重试 |
| 401 AUTH_INVALID / SESSION_REVOKED | 访问身份失效 | 重新认证，保留未发草稿 |
| 403 FORBIDDEN / MEMBERSHIP_REVOKED | 已知对象权限不足或成员撤权 | 停止订阅/发送，清理可控缓存 |
| 404 NOT_FOUND | 对象不存在或需隐藏其存在 | 不以不同文案泄漏跨用户对象 |
| 409 IDEMPOTENCY_CONFLICT / VERSION_CONFLICT | 重复键异内容或版本冲突 | 取当前快照，要求用户确认 |
| 410 CURSOR_EXPIRED | 事件保留过期 | 完整 resync，不无限重试旧 cursor |
| 422 CAPABILITY_UNSUPPORTED | 当前 adapter 无强制执行能力 | 禁用相应操作 |
| 429 RATE_LIMITED | 超限 | 按 retry_after_ms 退避 |
| 503 TEMPORARILY_UNAVAILABLE | 短暂不可用 | 同幂等键指数退避，不能假定失败未提交 |

## 身份、联系人与 Agent 管理 REST

下表不定义未决定的 human 登录认证方式；建立 session 后才可使用这些接口。

| 方法与路径 | 关键请求字段/鉴权 | 成功 data 的关键字段 |
| --- | --- | --- |
| GET /v1/me | human | account_id、kind、display_name |
| GET /v1/sessions | 当前 human | items：session_id、device_summary、last_seen_at |
| DELETE /v1/sessions/{id} | session 所属 human | revoked_at；同步失效相关连接 |
| POST /v1/contacts | human；target_account_id、client_request_id | contact_id、status、version；不暴露目标秘密 |
| POST /v1/contacts/{id}/decision | 对方 human 或 agent owner；decision=accept/reject、expected_version | contact_id、status、version |
| POST /v1/contacts/{id}/block | 联系关系当事 human；expected_version | status=blocked、version |
| GET /v1/contacts | human；page_token、limit | items、next_page_token |
| POST /v1/agents | human；display_name、adapter_kind、client_request_id | agent_id、owner_id、status=unbound、version |
| GET /v1/agents | human；scope=owned、page_token、limit | 自己管理的 items、next_page_token |
| GET /v1/agents/{id} | 有权见资料的 human | 有限资料、owner、online_state、integration_state |
| PATCH /v1/agents/{id} | owner；expected_version、display_name 或 status=disabled/active | 新 version、状态；unbound 不可直接改 active |
| PATCH /v1/agents/{id}/policy | owner；expected_policy_version、capability_policy | 新 policy_version；旧审批/在途任务按撤权规则处理 |

创建类 client_request_id 默认 UUID，按主体+动作唯一并校验请求摘要；不复用 message 的幂等命名空间。
配对后才允许 active，禁用后的恢复需 owner 确认策略且凭据仍有效；已撤销设备须重新配对。

## 会话与成员 REST

| 方法与路径 | 关键请求字段/权限 | 成功 data 的关键字段 |
| --- | --- | --- |
| POST /v1/conversations | human；kind=direct/group、participant_account_ids、title、client_request_id | conversation_id、kind、auth_version、members；direct 已存在返回 200 |
| GET /v1/conversations | human；page_token、limit | 授权 items、last_message 摘要、unread、next_page_token |
| GET /v1/conversations/{id} | 当前 active human member | 有限资料、当前成员/角色、visible_from_seq、auth_version |
| POST /v1/conversations/{id}/invitations | 群主/管理员；target_account_id、client_request_id | invitation_id、status、expires_at、version |
| POST /v1/invitations/{id}/decision | 被邀请 human 或 AI owner；decision、expected_version | status、membership_id（激活后）、version |
| PATCH /v1/conversations/{id}/members/{membership_id} | 群主；role、expected_auth_version | role、auth_version；群主转让须原子更新双方角色 |
| DELETE /v1/conversations/{id}/members/{membership_id} | 按角色移除或本人退出；expected_auth_version | left_seq、auth_version |
| DELETE /v1/conversations/{id} | 群主；expected_auth_version | status=closed、auth_version，停止新任务 |

direct 只允许两个固定参与者且联系人 accepted；group 至少一个 human，初建只激活创建者，其余参与者生成邀请。
邀请、角色、成员移除和解散接口仅用于 group；direct 一期不提供退出/重开，通过 contact 阻止新的发送，保留现有历史规则。
group 创建响应区分 active members 与 pending invitations，不能把待审批 AI 当成已入群。
成员请求的重复应用不得重复分配历史区间或系统消息；权限和并发规则见[账号与权限](账号与权限.md)。
AI owner 可用成员移除接口撤回自己的 agent；若 owner 不是群成员，只接受对应 membership_id 和自身授权，响应仅为撤回状态，不含 seq、正文或其它群资料。

## 发送消息与读取

| 方法与路径 | 请求字段 | 响应字段/语义 |
| --- | --- | --- |
| POST /v1/conversations/{id}/messages | client_message_id、text、mentions[]、可选 reply_to_message_id | 201 新建/200 幂等重试：message、runs[]；这是持久 ACK |
| GET /v1/conversations/{id}/messages | 可选 before_seq、limit 默认 50/最大 100 | items 按 seq 升序、next_before_seq、has_more、visible_from_seq |
| GET /v1/messages/{id} | human，逐对象检查会话/成员区间 | message 完整快照与 run 摘要 |
| POST /v1/conversations/{id}/delivery-receipts | through_seq；设备 session 从认证推导 | persisted_through_seq；本设备已接收可见消息，不是已读 |
| PUT /v1/conversations/{id}/read-cursor | through_seq | read_seq 单调不减、unread；只能标当前可见且存在的边界 |
| GET /v1/runs/{id} | 当前有权访问关联消息的 human | run 状态、attempt 摘要、响应 message、审批摘要 |
| POST /v1/runs/{id}/cancel | 发起者或紧急停止授权者；client_request_id | 202 cancel_requested 或 200 已终态；不承诺工具已停 |
| POST /v1/approvals/{id}/decision | 资源 owner；decision、action_digest、expected_policy_version | approval 状态；审批结果仍需 runtime 强制执行 |

| message 字段 | 类型与约束 |
| --- | --- |
| message_id / conversation_id | 服务端不透明 ID |
| seq / sender_account_id | 会话单调序号 / text 由服务端派生，system 为 null 并显示平台系统标签 |
| kind | text / system；system 仅平台写入 |
| client_message_id | human 发送 UUID；AI 响应用 run_id 关联，不借用此字段 |
| text / mentions | human text 默认最多 16 KiB，AI 聚合最多 256 KiB；mentions 是当前成员的 account_id 数组，去重，不能指向陌生账号 |
| reply_to_message_id | 必须在同会话且请求主体可见，只是引用，不自动触发被引用 AI |
| run_id / trigger_message_id | AI 响应关联的 run 与原触发消息；普通消息为空 |
| status / terminal_reason | draft/partial/final；draft/partial 终止原因可为 cancel/error/unknown，final 无失败原因 |
| revision / last_delta_seq | 聚合版本单调递增 / 最后已持久接收的增量序号 |
| created_at / updated_at | 服务端 UTC 时间 |

```json
{"client_message_id":"8a16f128-893c-4fb2-a165-e0abeab911c7","text":"请总结本次讨论","mentions":["agent-example"],"reply_to_message_id":null}
```

```json
{"request_id":"req-send","data":{"message":{"message_id":"message-example","conversation_id":"conversation-example","seq":"12","sender_account_id":"human-example","kind":"text","text":"请总结本次讨论","mentions":["agent-example"],"status":"final","revision":"1"},"runs":[{"run_id":"run-example","agent_id":"agent-example","state":"queued"}]}}
```

以上为最小响应示意，未列出的可选快照字段按字段表定义，客户端不能推测 AI 已执行。
去重键为 conversation_id+sender_account_id+client_message_id，保留与消息同生命周期；异内容返回冲突。
重试也先鉴权，离群后不能用幂等键取回旧正文；同键创建 message/run/outbox 的事务只提交一次。

## human WSS envelope 与认证

路径 `/v1/events`，使用标准 WebSocket JSON；Native 客户端可用 bearer，跨端统一推荐一次性 ticket。
POST /v1/ws-tickets：human 已认证，body audience=human_events；返回 ticket、expires_at，默认 30 秒一次性使用。
握手只携短期 ticket，网关不记查询参数，浏览器严格校验 Origin，所有端校验受众；禁止 URL 放 refresh token 或 runner credential。
ticket 绑定 human session，session 撤销、account 禁用会主动断开并逐事件复查。

| envelope 字段 | 含义 |
| --- | --- |
| v / type / request_id | 版本 / 事件类型 / 控制请求关联号 |
| event_id / cursor | 持久事件身份 / 该 human 的主体游标，控制帧可省略 |
| conversation_id / seq | 相关会话 / 可选关联消息序号；不等于 event cursor |
| payload / occurred_at | 事件内容 / 服务端提交时间 |

```json
{"v":"aichat.v1","type":"message.updated","event_id":"event-example","cursor":"84","conversation_id":"conversation-example","seq":"13","payload":{"message_id":"answer-example","revision":"3","status":"partial","last_delta_seq":"2"},"occurred_at":"2026-10-24T12:00:00Z"}
```

客户端 hello 发送 last_cursor；welcome 返回 current_cursor、heartbeat_seconds=20、max_frame_bytes=65536。
客户端每次持久应用事件后发送 client.ack{cursor}，只表示事件消费进度，不等于消息送达、已读或任务完成。
仅收到 revision 元数据不能把正文版本标为已应用；先应用完整快照或连续 delta，缺内容则持久记录待补拉项再推进事件游标。
heartbeat/pong 超过 60 秒无响应关闭；错误使用 error 帧，含 code、request_id、retry_after_ms，与 REST 语义一致。
Nest WsAdapter 需将 envelope 解析为 type/payload，不能假定其默认 event/data 直接兼容此协议。

## 事件种类与恢复

| type | payload 关键字段 | 应用方式 |
| --- | --- | --- |
| message.created / message.updated | message_id、revision、状态/快照摘要 | 依 message_id+revision 合并，必要时 REST 取完整文本 |
| message.delta | message_id、run_id、delta_seq、revision、text | 连续序号追加，缺片取快照，不能重复追加 |
| member.changed / conversation.closed | auth_version、membership 摘要 | 更新权限并清理旧订阅，不能据此读取旧历史 |
| run.updated | run_id、state、response_message_id、safe_summary | 更新任务卡，不生成新聊天消息 |
| approval.requested / approval.updated | approval_id、状态、参数摘要 | 只投递有权审批者，不发送完整秘密参数 |
| agent.presence | agent_id、online_state、integration_state | 只给有权看资料者，在线不等于厂商可用 |
| stream.checkpoint / stream.resync_required | next_cursor / reason | 前进被过滤位置或重新取快照 |

GET /v1/events?after_cursor=...&limit=... 返回授权 items、next_cursor、has_more；limit 默认 100/最大 500。
被移除主体可接收只含自身 membership 撤销的 member.changed 墓碑，不含群正文或其他成员；这不恢复任何会话读取权。
cursor 按 human 接收主体分配，event_id 全局唯一；重投沿用原 event_id 和接收主体 cursor。
客户端只按返回 next_cursor 前进，不等待连续整数，也不把 conversation seq gap 当作网络丢包证明。
撤权后已经分配的事件逐项过滤，响应/心跳提供扫描过的位置；不能因不可见项造成无限等待。
事件默认保留 7 天，cursor 超期返回 410 CURSOR_EXPIRED；消息留存不因事件过期而删除。
GET /v1/sync-snapshot 返回 snapshot_id、snapshot_cursor、授权会话/成员/读游标摘要、每会话最新一页消息和 next_page_token。
快照在一致性读中物化，GET /v1/sync-snapshot?page_token=... 继续会话分页；旧历史仍使用消息接口 before_seq，不混用 token。
分页 token 绑定 snapshot_id、主体、session 和有效期，默认 5 分钟；每页仍复查最新权限，过期重建快照。
客户端先完成快照，再接 snapshot_cursor 之后的事件；outbox 延迟导致的重复以 message revision 去重。
重新授权只获得新 membership 区间，重连不能恢复此前被移除会话；后台缓存恢复同样遵守最新权限。

## 流式聚合、回执与终态

run 首次获准 start 时预留一个 draft 响应 message 与 seq；无输出的排队任务不制造虚假 AI 回答。
首片后为 partial，每片增加 revision 并持久更新聚合文本；断片回快照，不以客户端拼接作为最终答案。
task.finish 以短 final_text 或匹配 final_content_hash 的已持久聚合文本确认最终答案，校验 last_delta_seq；与 run succeeded 同事务置 message final。
取消/失败/未知保留 partial 和 terminal_reason；若从未输出，则保留空 draft 并标相同终止原因，仅展示任务失败卡。
终止后的 draft/partial 由关联 run 终态识别为已停止，不能继续显示生成中；禁止迟到 delta 修改它。
AI 最终文本默认最大 256 KiB，超过 WSS 帧上限时只发摘要并由 REST 拉取快照。
持久 ACK、设备送达、read_cursor 和 run succeeded 分别记录，任何一个都不能推断其他状态。
回调重复只返回已持久回执；旧 attempt/fence、终态后的冲突 finish 不得生成第二条答案。

## 限流、背压与离线路径

设计默认每 human 每分钟 60 次发送、同会话每秒 5 条；配对匿名入口按 IP 与 agent 双维限流，默认每分钟 5 次创建。
WSS 单帧默认 64 KiB，连接待发队列默认 1 MiB；超限发 BACKPRESSURE 并可关闭 1013，客户端从已持久游标恢复。
runner 上游输出超过接收窗口须暂停读取或停止任务并报错，不能无限内存缓冲或静默丢 delta。
网络错误按 1/2/4 秒递增加随机抖动，最大 30 秒；状态查询与同幂等键重试不新建任务。
App 离线草稿不显示已发送；human 消息已持久而 AI 离线则显示 queued，到排队截止后 failed。
取消中断、设备重启和未知副作用按[Connector 状态机](统一AI接入.md)处理，静态文档核对不代表这些路径已经实测。
