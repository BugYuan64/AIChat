# 统一 AI 接入

## 协议边界与目标

本文是 AIChat Connector v1、平台设备配对和 runner 任务通道的权威契约，全部待实现。
客户端消息与共用 envelope 见[消息契约](消息与HTTP-WSS契约.md)，权限见[账号与权限](账号与权限.md)。
Agent 运行时含会话、工具和执行控制；模型 API 通常只负责推理请求，两者不能混称完整 Agent 接入。
Connector 是自定义平台协议，adapter 桥接上游差异；OpenAI-compatible endpoint 不代表兼容全部 CLI 或工具权限。
runner 在 Windows/Linux 用户设备主动出站 WSS，后端独立部署；不把本地 stdio 或 CLI 端口暴露公网。

| 候选 | 计划路径 | 实现前核对 | 当前状态 |
| --- | --- | --- | --- |
| Hermes | 评估本地 API server 的 HTTP 与会话能力 | 版本、隔离、流式、工具、取消与审批 | 未启动本项目业务连接 |
| Codex | 本地 runner 封装 app-server stdio | 消息映射、线程隔离、审批、取消、版本 | 未启动本项目 app-server 业务 |
| Claude | 官方允许的 API/运行时 adapter 待选 | 可用接口、许可、工具与取消 | 未核对具体接入协议 |
| Gemini | 官方允许的 API/运行时 adapter 待选 | 版本、权限及会话隔离 | 未核对具体接入协议 |
| ZCode | 依据官方产品与配置资料调查 | 协议、许可、取消与审批 | 候选，无通用扫码 API 承诺 |

上游事实及固定来源编号仅在[设计决策与验收](设计决策与验收.md)说明；当前主机登录状态不作为业务连接证据。
AIChat 与 AgentForge 无已集成关系；未来编排器也必须使用同一授权入口，不能旁路平台权限。

## 配对对象与状态

human 先创建 agent，再将非秘密 agent_id 提供给 runner 发起配对。
pairing 固定 agent_id（请求目标）、由服务器推导的 owner_id、设备摘要与权限申请，批准时不能换绑对象。
状态为 pending → approved → consumed；pending 可转 denied/expired/revoked，approved 可转 revoked/expired。
设备绑定目标是 owner_id + agent_id + runner_id；一个 pairing 只签发一次持久 runner credential。
二维码只含短期 public_reference 或 user_code 及验证页面地址，不含 device_code、持久 token 或厂商 key。
平台流程受设备授权思想启发，不宣称完整 OAuth RFC 兼容；厂商授权是另一个独立步骤。

## 配对 REST 契约

所有请求 HTTPS，错误沿用共用错误结构；匿名入口限速，不提供账号存在性枚举。

| 接口 | 认证与关键请求字段 | 成功响应 |
| --- | --- | --- |
| POST /v1/pairings | 匿名；agent_id、runner_name、device_fingerprint、adapter_kind、requested_capabilities | 201：pairing_id、public_reference、user_code、verification_phrase、verification_uri、device_code、expires_at、interval_seconds |
| POST /v1/pairings/lookup | human；public_reference 或 user_code 二选一 | 200：pairing_id、agent_id、owner_id、设备摘要、权限、验证短语、expires_at、version |
| POST /v1/pairings/{id}/approve | owner human；expected_version、confirmed_fingerprint、granted_capabilities | 200：status=approved、version；不向手机返回设备凭据 |
| POST /v1/pairings/{id}/deny | owner human；expected_version | 200：status=denied |
| POST /v1/pairings/{id}/revoke | owner human；expected_version | 200：status=revoked；已消费须改撤销 runner |
| POST /v1/pairings/token | 匿名但必须持有 secret device_code | 200：首次成功返回 runner_id、credential_id、runner_credential、access_token、expires_in |
| POST /v1/runner/access-tokens | runner credential；client_nonce | 200：短期 access_token、expires_in、agent_policy_version |
| GET /v1/agents/{id}/runners | owner human | runner_id、设备摘要、status、credential_version、last_seen_at；无秘密 |
| GET /v1/agents/{id}/memberships | owner human | 已批准的群标识、显示名、membership_id、状态；无群正文或其他成员 |
| POST /v1/runners/{id}/rotate | owner human；expected_credential_version | 200：status=re_pair_required；设备重新请求 pairing，不在手机发持久凭据 |
| POST /v1/runners/{id}/revoke | owner human；reason、expected_credential_version | 200：revoked_at，关闭连接并停止任务 |

| 字段 | 类型/约束 | 安全含义 |
| --- | --- | --- |
| agent_id | 不透明字符串，必须指向可配对 agent | owner 从 agent 记录推导，忽略/拒绝外传 owner_id |
| device_fingerprint | 设备摘要字符串 | 供人核对，不因设备自报名而认定可信 |
| public_reference | 随机短期公开引用，设计默认至少 128 位随机量 | 只查待审批信息，不可兑换凭据 |
| user_code | 设计默认 8 位易读字符 | 手机手输路径，须登录 owner 并审批 |
| device_code | 高熵秘密，只在创建响应给 runner | 保存在设备内存，不显示二维码，不落日志 |
| expires_at / interval_seconds | UTC 时间 / 整数秒 | 默认 5 分钟有效、5 秒轮询，服务端时间权威 |
| requested/granted_capabilities | 能力数组 | 批准值不可超申请、owner 策略和 adapter 实测上限 |
| expected_version | 正整数 | 防重复批准、竞态与对象变化 |

以下是虚构字段示意，不是当前可运行接口或真实凭据：

```json
{"pairing_id":"pairing-example","public_reference":"public-example","user_code":"ABCD2345","verification_uri":"https://aichat.example/pair","device_code":"<仅设备持有的秘密>","expires_at":"2026-10-24T12:05:00Z","interval_seconds":5}
```

手机扫描后显示服务域名、owner、agent、设备名/指纹、验证短语与权限，必须明确点击批准。
runner 与手机核对同一验证短语；外部网页、聊天中转二维码或冒充设备名不能成为自动批准依据。
手动路径输入 user_code 后使用同一审批页面与权限检查，不设管理员万能绕过码。
lookup 对非 owner 返回统一 NOT_FOUND；approve 按 agent→pairing 顺序锁定并检查有效策略，跨 owner 一律失败。
重复扫描只展示当前状态；重复批准在同一决定下返回既有结果，版本或权限不一致返回 VERSION_CONFLICT，绝不再次签发凭据。
轮询 pending 返回 400 PAIRING_PENDING，过快返回 429 SLOW_DOWN 并增加间隔；拒绝/过期/撤销返回 PAIRING_DENIED/PAIRING_EXPIRED/PAIRING_REVOKED。
token 首次成功在事务内消费 pairing 并写 credential 摘要，只有赢得消费的响应携带一次明文。
并发/重复兑换返回 409 PAIRING_CONSUMED，不重发凭据；首次响应丢失时撤销新设备并重新配对，不缓存明文等重试。
未批准、过期、拒绝、撤销均不能签发 access token；二维码截图或重放本身不能取得设备身份。

## 凭据生命周期与恢复

runner_credential 高熵随机，服务端仅存带服务端保护材料的 hash/摘要与版本、范围、时间，不存可恢复明文。
设备使用 OS 安全存储；无可验证安全存储时不得承诺持久安全，部署前决定替代方案。
短期访问 token 默认 10 分钟，绑定 audience=runner、runner_id、agent_id、owner_id、credential_version。
每次连接和任务操作复查有效版本，不能等 token 自然过期才生效撤销。
轮换先撤旧 credential 和连接，再创建新 pairing，接受短暂停机；不允许无限期双凭据并行。
设备遗失从 human 接入管理撤销；新设备重新配对，不复制旧 credential，不要求展示历史秘密。
token 续期失败只重试认证，不把未确认任务重新执行；human 登录失效与 runner 认证错误分开提示。

## runner WSS 与能力协商

路径 `/v1/runner/events` 使用 Authorization bearer runner access_token；禁止 human 票据或 URL 中的持久 token。
复用 v=aichat.v1、type、request_id、payload；控制消息不使用 human 事件 cursor。
连接后先 runner.hello，载明 connector_version=1、runner_id、adapter_kind/version、capabilities 与本地未结任务摘要。
服务器返回 runner.welcome，含 connection_id、heartbeat_seconds、lease_seconds、max_inflight、effective_capabilities、agent_policy_version。
默认心跳 20 秒、60 秒无有效响应判离线；单 runner 默认最大 2 个在途任务，单 agent 默认并发 1。
能力项至少有 text、stream、cancel、tool_approval、workspace_isolation、side_effect_free；缺项视为不支持。
声明不能直接提权，平台只开启经 adapter 验证且被 owner/会话策略允许的能力；不支持版本返回 VERSION_UNSUPPORTED 并关闭。
连接互斥以 runner connection epoch 更新；旧连接不能继续领任务或提交结果。

## task 事件字段

下表为平台控制消息，业务 AI 输出只经合法 run 聚合为 message，不允许 runner 任意发聊天消息。
任务控制帧的共同标识为 run_id、attempt_id、fencing_epoch、policy_version，下表“上述标识”均含这四项；连接 hello/welcome 不绑定具体 run。

| type | 方向 | payload 必需字段及效果 |
| --- | --- | --- |
| task.dispatch | 服务端 → runner | 上述标识、lease_until、agent_id、conversation_id、trigger_message_id、response_message_id=null、context、policy、deadline_at |
| task.ack | runner → 服务端 | 上述标识；只确认接收，不允许开始执行 |
| task.start | runner → 服务端 | 上述标识、operation_id；申请执行许可 |
| task.start.allowed | 服务端 → runner | 上述标识、response_message_id、lease_until；事务登记 running 并预留响应消息后才发 |
| task.heartbeat | runner → 服务端 | 上述标识、progress_summary；续约，不扩展 deadline_at |
| task.delta | runner → 服务端 | 上述标识、delta_seq、text；按序持久聚合，接收返回 task.received |
| task.finish | runner → 服务端 | 上述标识、operation_id、final_text 或 final_content_hash、usage、last_delta_seq；提交成功终态 |
| task.error | runner → 服务端 | 上述标识、operation_id、code、safe_summary、side_effect_status；失败或未知 |
| task.cancel | 服务端 → runner | 上述标识、reason；要求停止，不代表已停止 |
| task.cancelled | runner → 服务端 | 上述标识、operation_id、side_effect_status；可确认停止才接受 cancelled |
| task.received | 服务端 → runner | request_id、run_id、attempt_id、accepted_delta_seq、state；仅持久化接收回执 |
| task.resume | runner → 服务端 | 上述标识、local_state、last_acked_delta_seq；请求状态核对，不能自行续跑 |
| task.resume.result | 服务端 → runner | 当前 state、有效 epoch、next_delta_seq、may_continue；仅有效 running attempt 可继续 |
| tool.approval.request | runner → 服务端 | run_id、attempt_id、fencing_epoch、action_digest、action_summary、policy_version；先暂停操作 |
| tool.approval.result | 服务端 → runner | approval_id、action_digest、decision、expires_at、policy_version；匹配且未过期才允许 |

context 是服务端按成员区间交集选定的 message 摘要/正文及独立 runtime_session_key，不是任意查询历史的凭证。
context 按预算和帧大小选取，不能裁掉触发消息；无法容纳返回 CONTEXT_TOO_LARGE，不偷偷扩大传输限制。
policy 包含工具白名单、工作区、预算与审批主体；runtime_session_key 至少按 agent+conversation 隔离，重新入群轮换。
task.finish 的 final_text 与 final_content_hash 二选一；短文本最多 32 KiB，较大答案用已连续持久聚合文本的 UTF-8 SHA-256 确认，聚合总上限 256 KiB。
服务端核对 last_delta_seq 与摘要，缺片拒绝终结；摘要不符报 FINAL_CONTENT_MISMATCH，禁止将截断文本当最终成功。
task.start/finish/error/cancelled 的 operation_id 每个逻辑操作唯一，且同一 ID 不得跨 type 复用；同 type 同 ID 同内容重试返回原回执，换内容返回冲突。
task.delta 以 attempt_id+delta_seq 去重，同序号不同内容报 IDEMPOTENCY_CONFLICT；不连续报 DELTA_GAP 并返回 next_delta_seq。
tool.approval.request 返回 approval_id 和待审批状态；human 决策接口见[消息契约](消息与HTTP-WSS契约.md)。

## 租约、重试与取消

run 状态：queued → leased → running → succeeded/failed/cancelled/unknown；leased 可因安全回收返回 queued。
running/leased 可进入 cancel_requested，未开工的 queued 可直接 cancelled；unknown 是停止自动调度的终态。
attempt 状态：leased/running/succeeded/failed/cancelled/unknown；每次新租约生成新 attempt 并递增 fencing_epoch。
设计默认租约 60 秒，每 20 秒续租，dispatch 10 秒未 ack 可回收；start 必须复查仍有效的租约与成员权限。
runner 未收到 start.allowed 不得执行；许可响应丢失先 resume 核对状态，本地账本不能证明未执行时不能盲目开工。
领取时锁队列行并写 attempt；所有回报须匹配当前 attempt、epoch、runner 和策略版本，旧 epoch 返回 STALE_FENCE。
重连先 resume；仅租约未过期、授权未变且本地账本可核对时，将 attempt.connection_epoch 原子迁移至新连接，不新增 attempt 或重放操作。
仅 leased 且从未批准 start 的任务可安全自动重派；旧 attempt 置 failed 并记 lease 超时，run 回 queued，默认最多 3 次领取，超过则 failed。
running 后断线/进程崩溃/租约到期且无法确认结果转 unknown，不自动重放文件写、命令、推送等副作用。
纯只读自动重试也需实测 side_effect_free 并显式开启策略，一期默认关闭；人工确认风险后重新发送 human 消息，以新 trigger_message_id 创建 run，reply_to_message_id 指向原触发消息，不复用原根 run 唯一键。
租约和 fence 防止旧结果写进数据库，不能阻止失联的外部进程已执行副作用；设备隔离及审批必须由 runtime 强制。
取消先持久 cancel_requested，再发 task.cancel；默认 15 秒内未确认停止转 unknown，保留 partial，不伪造 cancelled。
取消期间收到 finish 不将 run 改为 succeeded，记录迟到结果摘要并核对停止/副作用；终态回调不复活任务或追加新答案。
撤权后拒收正文并丢弃待推送内容，必要审计仅保留摘要；禁用/撤销对在途任务同样触发停止与未知结果处理。

## 触发、预算与有限协作

默认 human-agent 私聊或 human 在群内结构化 @agent 才产生 run；AI 输出 @ 默认不触发。
同一触发消息和目标 agent 仅一个根 run；重复投递不能创建新任务。离线任务默认等待至创建后 10 分钟。
一次 human 群消息默认最多 @3 个 AI；单 run 默认执行时限 5 分钟，adapter 不支持硬取消则禁止相应高风险能力。
协作在 D6 才实现，默认关闭；群主开启且涉及的 agent owner 同意上下文和能力后才可使用。
设计默认每条协作链最多 4 轮、并发 2、总计 20,000 归一化 token、总时限 10 分钟，均可由策略下调。
token 不能可靠计量时预留保守上限，不允许无限额度；费用换算需另核厂商价格，不在本轮承诺。
平台事务预留轮次与预算，AI 只提交下一步建议；重复建议按父 run+目标+轮次去重。
到限、取消、成员撤权、owner 禁用或审批拒绝即停止派生；用户停止整链优先于 AI 的继续建议。

## 失败处理与验收边界

AUTH_INVALID/CREDENTIAL_REVOKED 要停止连接；CAPABILITY_UNSUPPORTED 禁用能力，不假装成功。
LEASE_EXPIRED/STALE_FENCE 不重发业务输出；RATE_LIMITED/BACKPRESSURE 按 retry_after_ms 暂停，状态不凭本地猜测。
runner 本地账本仅存最小状态及去重摘要，不记录永久厂商秘密或无界会话正文；磁盘损坏转未知并人工处理。
真实接入至少验证请求、会话隔离、流式、取消、审批、断线和重启；只会返回一段测试文本不算完整业务验收。
最小正常链路为 hello→welcome→dispatch→ack→start→start.allowed→delta/received→finish/received；任一失败按上述状态和错误码处理。

```json
{"v":"aichat.v1","type":"task.delta","request_id":"req-delta","payload":{"run_id":"run-example","attempt_id":"attempt-example","fencing_epoch":"1","policy_version":"policy-example","delta_seq":"1","text":"开始总结。"}}
```

验收证据与待决策见[设计决策与验收](设计决策与验收.md)。
