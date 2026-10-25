# AIChat

一个让人类用户与 AI 使用独立账号、通过私聊和群聊协作的聊天应用。名称暂沿用当前目录名；与 AgentForge 的产品归属尚未确定。

**当前阶段：实施进行中（2026-10-25 起进入编码）。** 已实现后端、连接器及移动端主要框架；H5 与后端已于 2026-10-26 部署至 **https://aichat.wsnbb.shop**。Android 真机、真实模型厂商接入和完整产品验收仍待完成。

**2026-10-26 审核与部署更新：** 已修复登录、权限、并发凭据、消息恢复、连接器重连与租约问题；分域版本后端 SQLite/PostgreSQL 两种环境均 52 项通过，连接器 57 项、当前前端 8 项通过。Docker、迁移、备份恢复、HTTPS 登录与 WSS、应用重启已实测。详见 [项目审核记录](docs/项目审核记录.md) 和 [部署说明](deploy/README.md)。群邀请接收 UI、真实模型和 Android 真机验收仍未完成。

**域名分工：** H5 使用 `https://aichat.wsnbb.shop`（橙云）；Android、H5、连接器及其他客户端统一访问 `https://api.aichat.wsnbb.shop`（灰云）。已实现精确来源 CORS 与缓存策略。按用户要求不保留未上线旧版本的 API 入口和地址迁移。

> **分支与选型说明（2026-10-25）**：`master` 实现分支与 `main` 设计稿分支已合并（两条独立根历史，合并提交保留双方设计稿与实现）；服务端技术栈经用户批准确定为 Python+FastAPI（设计稿 D-02 修订记录见 [docs/设计决策与验收.md](docs/设计决策与验收.md)），实施契约与设计稿的其余差异集中登记在 [PROTOCOL.md §11](contracts/PROTOCOL.md)。

## 已确定的方向

- 先开发手机 App，首个交付目标为 Android；H5、微信小程序后续适配。
- 人类和 AI 都有自己的账号、资料、联系人与会话身份，支持私聊和创建群聊。
- 统一 AI 接入包含**模型 API + 外部 Agent 连接器**。
- 外部 Agent 采用"连接器展示二维码，App 扫码并确认"的方式绑定。
- 实施以 [contracts/PROTOCOL.md](contracts/PROTOCOL.md) 为三方（服务端/连接器/移动端）唯一接口契约；修改契约必须同步三方。

## 技术栈（已实施）

客户端 uni-app + Vue 3 + TypeScript（`apps/mobile`，本地 H5 已构建，Android 尚未打包）；后端 Python + FastAPI 模块化单体 + SQLAlchemy 2 async + PostgreSQL（`services/server`，开发/测试可用 SQLite）；worker 循环与 API 同进程（v1 单实例，当前不要另启动独立 worker 或多 uvicorn worker）；连接器为独立 Python 包（`connectors/connector-runner`），含 echo 与 OpenAI 兼容两种适配器。Hermes、Codex、Claude、Gemini、ZCode 的真实适配仍在后续接入阶段逐一核验，不声明已兼容。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [统一接口规约](contracts/PROTOCOL.md) | **实施权威契约**：REST/WSS/事件/错误码/数值默认/模块接口规则/与设计稿差异清单(§11) |
| [产品需求](docs/产品需求.md) | 产品边界、账号与联系人、私聊群聊、页面职责、首版场景 |
| [项目最终架构](项目最终架构.md) | 当前与目标、方案取舍、模块、数据、通信、部署边界 |
| [AI 接入协议](docs/AI接入协议.md) | 两类接入、扫码绑定、接口草案、任务流、重试和权限 |
| [产品与交互](docs/产品与交互.md) | 设计稿：页面状态、文字线框、关键流程、异常反馈 |
| [账号与权限](docs/账号与权限.md) | 设计稿：统一身份、owner 隔离、群角色、历史授权时点 |
| [数据模型](docs/数据模型.md) | 设计稿：逻辑表、约束、关键事务与锁序 |
| [消息与HTTP-WSS契约](docs/消息与HTTP-WSS契约.md) | 设计稿：REST/WSS 契约、事件种类、流式聚合与恢复 |
| [统一AI接入](docs/统一AI接入.md) | 设计稿：配对状态机、runner WSS 任务协议、租约与取消 |
| [设计决策与验收](docs/设计决策与验收.md) | 设计稿：D-01~D-09 决策（含 D-02 修订）、数值默认、验收矩阵 |
| [阶段步骤](阶段步骤实现.md) | D0–D8 实施路线与各阶段验收门槛 |

另：`contracts/openapi.json` 为服务端自动生成的 OpenAPI 3.1 契约。

## 实际目录

```text
AIChat/
├─ apps/mobile/                 uni-app + Vue3 + TS 客户端（源码脚手架，见其 README）
├─ services/server/             FastAPI 模块化单体（aichat 包：core + 10 模块 + worker）
│  ├─ aichat/core/              config/db/信封/安全/依赖/outbox/限流
│  ├─ aichat/modules/           identity|contacts|conversations|messages|agents|pairing|runs|realtime|audit
│  ├─ aichat/runtime/           模型 API 适配器（OpenAI 兼容流式）
│  ├─ aichat/worker/            派发/扇出/维护循环 + 模型执行器（当前随 API 单进程运行）
│  ├─ migrations/ + alembic.ini 数据库迁移
│  └─ tests/                    集成与审核回归测试（52 项）
├─ connectors/connector-runner/ 连接器（配对客户端 + WSS 会话 + 本地账本 + 适配器）
├─ contracts/                   PROTOCOL.md + openapi.json
├─ tests/e2e/run_e2e.py         真实进程三方联调脚本
├─ deploy/                      docker-compose（PostgreSQL + 服务端）
└─ docs/                        设计文档
```

模块接口规则（统一约定，详见 PROTOCOL.md §9）：每模块 `models/schemas/service/router` 四件套；跨模块只走对方 Service 公开方法；异步集成一律经 outbox 事件扇出；统一锁序 conversation→run→attempt→message。

## 启动与验证

### 后端（开发，SQLite）

```bash
cd services/server
uv venv && uv pip install -e ".[dev]"        # 或 pip install -e ".[dev]"
python -m aichat.bootstrap init-db
python -m aichat.bootstrap admin --handle admin --password <密码>
python -m aichat.bootstrap invite --count 5
python -m uvicorn aichat.app:app --port 8000   # 文档见 /docs
python -m pytest                                # 集成测试
```

### 端到端联调（配对 → 私聊 → 连接器执行 → 事件）

先启动服务器（如上，端口 8765），然后：

```bash
cd services/server
AICHAT_SERVER_URL=http://127.0.0.1:8765 python ../../tests/e2e/run_e2e.py
```

### 连接器

```bash
cd connectors/connector-runner
uv venv && uv pip install -e ".[dev]"
python -m connector pair --server http://<服务器> --agent-id <AI账号ID> --name 我的电脑 --adapter echo
python -m connector run  --server http://<服务器>
```

### 生产部署

`deploy/docker-compose.yml`：PostgreSQL + 迁移 + 引导管理员 + uvicorn；TLS 由前置反向代理终止。密钥经环境变量注入（样例见 `services/server/.env.example`），不得入库。

H5 入口为 https://aichat.wsnbb.shop，API 基址为 https://api.aichat.wsnbb.shop；API/PostgreSQL 使用 Compose，H5 由同机现有 Docker Caddy 提供。部署目录、私有配置、运维与回滚见 [部署说明](deploy/README.md)。

## 验证状态（诚实清单）

| 项目 | 状态 |
| --- | --- |
| 后端集成与回归测试 | **SQLite 52/52、隔离 PostgreSQL 16 52/52 通过**；含并发、权限、票据、历史、租约、取消、配置和 CORS 回归 |
| 连接器单元测试 | **57/57 通过**（新增过期凭据、配对地址回退、结果重放、取消 fence、字节上限和公开错误脱敏回归） |
| 真实进程 E2E | **通过**：uvicorn 服务器 + 连接器 WSS（echo 适配器）+ App 模拟，配对→授权→私聊→连接器执行→流式回复→事件补拉全链路 |
| Alembic 迁移 | 初始迁移 + ws_ticket 会话绑定迁移（2026-10-25）已生成并可空库升级 |
| 移动端/H5 | `npm test` **8/8**、类型检查及 H5 构建通过；正式 H5→API 跨域请求通过；群邀请接收 UI 缺失，Android/小程序未真机运行 |
| 真实模型厂商 | **未接入**。模型通路用假流验证；OpenAI 兼容适配器已实现但未对真实供应商（智谱/OpenRouter 等）验证 |
| PostgreSQL/Docker 部署 | 正式库迁移到 head；容器 healthy；隔离备份恢复、应用重启及正式 HTTPS/WSS 验收通过 |
| 多实例/推送/小程序 | 未做（v1 单实例约束见 PROTOCOL.md §0） |

开发时不得把模型密钥、连接器令牌、聊天记录或本机配置提交到源码仓库。
