# AIChat 移动端（apps/mobile）

uni-app + Vue 3 + TypeScript + Pinia 的 AIChat 移动客户端源码脚手架。接口严格遵循 [`contracts/PROTOCOL.md`](../../contracts/PROTOCOL.md)（唯一权威契约），页面职责对应 [`docs/产品需求.md`](../../docs/产品需求.md) 第 7 节。

> 本目录只包含源码与配置，未执行 `npm install`，不含 `node_modules`，不含任何二进制资源与真实密钥。

## 目录结构

```text
apps/mobile/
├─ package.json            依赖声明（@dcloudio/uni-* 3.0.0-4020920240930001 系列）
├─ vite.config.ts          uni-app vite 插件装配（预留 /v1 代理注释）
├─ tsconfig.json           TS 配置（types: @dcloudio/types / vite/client / node）
├─ index.html              H5 入口模板
├─ shims.d.ts              *.vue / 环境变量类型占位
├─ src/
│  ├─ main.ts              createSSRApp + Pinia
│  ├─ App.vue              启动恢复登录态、前台启动/后台停止事件 WSS、强制登出广播处理
│  ├─ manifest.json        appid 留空；app-plus 基础配置（含扫码模块与相机权限）
│  ├─ pages.json           tabBar：会话/联系人/我的；其余页面普通注册（登录页为启动页）
│  ├─ api/
│  │  ├─ client.ts         统一请求封装（信封解包 / Bearer / 401 刷新一次 / 错误码→中文）
│  │  ├─ types.ts          与 PROTOCOL.md 字段一一对应的 TS 类型（大数一律 string）
│  │  └─ auth/contacts/chat/agents/pairing/runs.ts   按域拆分的接口模块
│  ├─ stores/
│  │  ├─ auth.ts           token/账号持久化（uni.setStorageSync）、登录/登出
│  │  └─ chat.ts           会话列表、按会话消息缓存、运行状态、事件游标持久化与事件应用
│  ├─ ws/events.ts         人类事件 WSS 客户端（票据、心跳、指数退避重连、HTTP 补拉）
│  ├─ pages/               10 个页面（见下）
│  ├─ styles/base.scss     全局公共样式（无 UI 组件库，全部手写）
│  └─ utils/misc.ts        大数十进制比较 / 幂等键生成 / 时间格式化
```

## 页面清单

| 页面 | 路径 | 职责 |
| --- | --- | --- |
| 登录/注册 | `pages/login/login.vue` | handle+密码登录、邀请码注册、服务器地址配置入口 |
| 会话（tab） | `pages/sessions/sessions.vue` | 会话列表（标题/最后消息/未读角标）、下拉刷新、发起聊天入口 |
| 联系人（tab） | `pages/contacts/contacts.vue` | 联系人列表、按账号名精确搜索、加联系人、待处理申请（收/发）、发消息、移除/拉黑、多选建群 |
| 我的（tab） | `pages/me/me.vue` | 本人资料、我的 AI 入口、扫码配对入口、服务器地址修改、退出登录 |
| 我的 AI | `pages/agents/agents.vue` | AI 列表（绑定/在线状态）、创建 AI |
| AI 详情 | `pages/agents/detail.vue` | 档案编辑、模型绑定表单与撤销、使用授权管理、连接器列表与撤销 |
| 聊天 | `pages/chat/chat.vue` | 消息列表（AI draft/partial/final、系统消息灰条、引用、@）、幂等发送与失败重试、@ AI 成员选择、AI 运行状态卡（停止/重试）、上拉加载历史、已读上报 |
| 群设置 | `pages/group/settings.vue` | 成员/角色展示、邀请（含 AI 所有权确认提示）、移除成员、退群、解散 |
| 扫码配对 | `pages/pairing/scan.vue` | 扫码或输码、连接器信息 + confirm_code 核对、选择本人 AI、批准/拒绝、5s 轮询状态 |
| 运行详情 | `pages/runs/detail.vue` | 运行状态/阶段/失败原因（脱敏）、停止、重试、跳转会话 |

## 运行方式

### 前置

- Node.js ≥ 18；HBuilderX 3.9+（App 真机运行）；后端 `services/server` 已启动。

### uni-app CLI（推荐）

```bash
cd apps/mobile
npm install
npm run dev:h5          # 浏览器开发（默认 5173 端口）
npm run build:h5        # H5 构建
npm run dev:app         # App 开发（需 HBuilderX 基座或自行配置基座）
npm run build:app
```

### HBuilderX

1. 用 HBuilderX「导入」`apps/mobile` 目录（CLI 工程结构，源码位于 `src/`）。
2. 先在终端执行 `npm install`。
3. HBuilderX 中通过「运行 → 运行到浏览器 / 运行到手机或模拟器」执行；如 HBuilderX 无法直接识别 CLI 工程，可使用其「外部命令」运行上述 npm scripts，或用 HBuilderX 新建 uni-app Vue3/TS 项目后将 `src` 目录内容拷入对照迁移。
4. App 真机运行需要在 HBuilderX 中配置自有证书/云打包（见「未实现项」）。

## 服务器地址配置

优先级（高 → 低）：

1. **运行期设置**：登录页「服务器设置」或「我的 → 服务器地址」，写入本地存储键 `aichat.server_base`；
2. **构建期预置**：项目根目录 `.env.local` 中 `VITE_AICHAT_SERVER=http://192.168.1.10:8000`（不提交仓库）；
3. **默认值**：`http://127.0.0.1:8000`。

要求填写完整 origin（`http://` 或 `https://` 开头，不带路径）。WSS 地址自动推导：`http→ws`、`https→wss`，端点为 `<base>/v1/realtime`。修改地址后重新登录即可生效。

H5 开发跨域：后端开启 CORS，或放开 `vite.config.ts` 中注释的 `/v1` 代理并将客户端地址指向开发服务器同源反代。

## 协议遵循要点

- **信封**：所有响应按 `{"request_id","data"|"error"}` 解包（`api/client.ts`）；错误码映射为中文提示（`describeError`）。
- **认证**：自动携带 `Bearer`；`AUTH_INVALID/SESSION_REVOKED`（401）时以单飞方式调用 `POST /v1/auth/refresh` 恰好一次并重放原请求；仍失败清理凭据、广播事件、跳登录页。
- **幂等**：发送消息携带 `client_message_id`，失败重试沿用同一键（§4）；私聊创建携带 `client_request_id`（§3）。
- **事件（§5）**：`ws/events.ts` 换 30s 一次性票据 → 首帧 `{"type":"ticket"}` → `welcome(current_cursor, heartbeat_seconds)`。持久事件按 **event_id 去重**、按 **cursor 单调**应用（与 HTTP 补拉共用同一裁决函数 `stores/chat.applyEventFrame`）；`message.updated` 按 **revision 合并**；`run.delta` 追加内存流式缓冲（chunk_index 幂等），final 后清除缓冲改用权威文本；断线立即 `GET /v1/events?after=<cursor>` 补拉 + 指数退避（1s→60s 抖动）重连；`410 CURSOR_EXPIRED` 触发全量 resync；心跳 ping 默认 20s、60s 无帧判离线。
- **前台策略**：App 退后台停止 WSS、回前台重连并补齐（对应产品需求「前台实时，恢复前台补齐」）。

## 已知假设（等待与服务端实现联调对齐）

1. `GET /v1/contacts` 的 items 除 `account + relation` 外需带 `request_id`（`pending_incoming` 时）供 decision 使用；规约未明列该字段。
2. `GET /v1/conversations`、`GET /v1/conversations/{id}`、消息分页、`Run`/`Agent` 对象的**信封内字段名**规约未逐字段锁定，`api/types.ts` 中的命名为当前客户端假设。
3. 配对决策 `POST /v1/pairings/{id}/decision` 规约仅锁定 `{decision, confirm_code, expected_version}`；页面上的「选择本人 AI」以可选字段 `agent_id` 附带提交，服务端按 §0「未知可选字段可忽略」处理（不支持时以配对单创建时的 agent_id 为准）。
4. `DELETE /v1/agents/{id}/grants` 的 `human_account_id` 以请求体传递，如服务端要求 query 参数需调整 `api/agents.ts`。
5. 首次运行（无本地游标）以 welcome 的 `current_cursor` 为基线，历史通过会话/消息 HTTP 快照获得，不回放更早事件。

## 当前实现范围与未实现项

**已实现（源码级）**：登录/邀请注册、会话/联系人/我的三个 tab、私聊与群聊（发送/引用/@/重试/历史分页/已读上报/未读角标）、AI 档案与模型绑定表单、使用授权、连接器列表与撤销、扫码配对确认全流程、运行详情与停止/重试、事件 WSS + HTTP 补拉 + 断线重连 + 全量 resync。

**未实现 / 待补**：

- App 正式打包（证书、云打包配置、应用图标与启动图）、厂商推送与后台到达率（首版范围外）；
- tabBar 图标与头像图片（未引入任何二进制资源，文字占位）；
- 群名修改、任命管理员、转让群主、AI 回复策略配置：PROTOCOL.md §3 尚无对应接口；
- 图片/文件/语音消息、Markdown 富渲染（首版仅纯文本）；
- 多端同步细节优化、离线消息本地数据库持久化（当前消息仅内存缓存 + 服务端快照）；
- 邀请（invitations）待确认列表页：无 `GET /v1/invitations` 类接口，当前仅能被动接收事件提示；
- 微信小程序端 `uni.request` 域名白名单等平台侧配置。
