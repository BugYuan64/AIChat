# AIChat 部署与运维

## 当前部署（2026-10-27）

- H5 入口：**https://aichat.wsnbb.shop**，Cloudflare 橙云；浏览器页面导航保留在该域名。
- 所有平台 API 基址：**https://api.aichat.wsnbb.shop**，Cloudflare 灰云，A 记录为 `35.73.46.1`；人类 WSS 为 `wss://api.aichat.wsnbb.shop/v1/realtime`，连接器 WSS 为 `/v1/connectors/realtime`。
- SSH 用户：`ubuntu`；源码目录：`/home/ubuntu/aichat`。
- PostgreSQL 16 与 FastAPI 由该目录 `deploy/docker-compose.yml` 管理；原 `deploy_pgdata` 数据卷保留，API 只绑定 `127.0.0.1:8000`，单 uvicorn worker，容器用户为非 root `aichat`。
- H5：以 `VITE_AICHAT_SERVER=https://api.aichat.wsnbb.shop` 构建，当前发布目录为 `/usr/share/caddy/aichat/releases/mobile-fixes-20261027`（详情页侧栏返回所属列表、切换配对请求时作废旧确认码、草稿恢复携带提及与引用；上一版本 `login-fix-20261027` 保留可回切）。本次仅替换 H5 静态文件，后端源码、镜像（`340c9a6d5d34`）、Compose 与 Caddy 配置均未改动。按用户要求不保留未上线旧版本的地址迁移、API 入口或旧资源兼容。
- HTTPS：复用既有 Docker 容器 `cohost-proxy-caddy-1`（host 网络），站点文件为 `/etc/caddy/Caddyfile.d/aichat.caddy`，对应仓库模板 [aichat.caddy](aichat.caddy)。H5 文件经已存在的 `/usr/share/caddy` 只读挂载提供；`/v1/*`、健康与接口文档反代至 API，支持 WSS。
- TLS：H5 浏览器侧证书由 Cloudflare 管理，回源继续使用 Caddy 的有效证书；灰云 API 使用 Caddy 自动续期的 Let's Encrypt 证书，本次 API 证书到期为 2027-01-24 00:12（UTC+8）。
- H5 域名仅提供静态页面及有效的配对跳转，`/v1/*`、`/healthz`、`/docs` 等旧后端路径返回 404。旧 IP `/aichat/*` 反代已从主 Caddyfile 精确移除；后端只经新 API 域名访问。

## 跨域与橙云缓存

后端仅允许 `https://aichat.wsnbb.shop` 跨域；认证继续用 Authorization Bearer，不使用跨域 Cookie。允许实际使用的方法与 Authorization/Content-Type/X-Request-Id，预检缓存 600 秒。原生 Android/连接器不受浏览器 CORS 限制，但仍需相同的后端认证。

HTML 入口使用 `Cache-Control: no-store`，带内容哈希的 `/assets/*` 使用一年 immutable 缓存，API 使用 `no-store`。已核对经过 Cloudflare 的响应头及真实浏览器跨域请求；未通过工具更改 Cloudflare 控制台设置。控制台不要对 HTML/API 强制套用忽略源站缓存头的 Cache Everything 规则，回源 TLS 宜设 Full (strict)。

拆分的代价包括额外的 DNS/TLS 配置、浏览器跨域预检和缓存发布管理。API 灰云仍公开源站 IP，因此同机 H5 橙云不能完全隐藏服务器地址。

本次修复与部署配置统一纳入 GitHub `main`，当前源码版本以 `git log -1` 为准。初次上线基于 `0f2d7c5f67a7a95e0e24a3fd1c7990eecc0d3c65` 加本次修复；运行镜像源码已与交付文件逐项校验。Git 提交推送本身不自动重建或重启线上容器，部署时同时记录源码版本与下述镜像 ID。

## 登录与私有配置

管理员账号为 `admin`，密码于 2026-10-26 应所有者要求轮换（bootstrap 不覆盖已有账号，变更经容器内服务端脚本直调服务层完成，并同步吊销 admin 既有登录会话）；同日另建普通账号 `bjy`（服务层直调创建，密码弱于注册接口 8 位下限，仅联调使用）。当前密码以服务器 `/home/ubuntu/aichat/deploy/.env` 的 `ADMIN_BOOTSTRAP_PASSWORD` 为准（已同步轮换）；文件权限 600，秘密未写入源码、部署记录或聊天输出。分域切换后，浏览器若遗留旧版本写入的 localStorage 服务器地址，登录会一直超时：在登录页「服务器设置」改回 `https://api.aichat.wsnbb.shop` 或清除该站点数据即可。

该文件另含数据库密码、JWT 签名密钥、Fernet 主密钥，以及非秘密设置：

```dotenv
AICHAT_PUBLIC_BASE_URL=https://aichat.wsnbb.shop
AICHAT_CORS_ORIGINS=["https://aichat.wsnbb.shop"]
AICHAT_BIND=127.0.0.1
```

Compose 强制四项秘密存在；生产拒绝短于 32 字节的 JWT 密钥及缺失/无效的 Fernet 主密钥。管理员引导从环境读取密码，不拼接进 shell 命令；已有账号会跳过，修改 `.env` 不会重置已有管理员密码。当前客户端没有密码修改界面。

## 本次实际验收

| 检查 | 结果 |
| --- | --- |
| SQLite 后端完整测试 | 分域版本 52/52 通过 |
| 隔离 PostgreSQL 16 后端完整测试 | 分域版本 52/52 通过；临时 fixture 使用独立验收库并逐例重建表，不触碰业务库 |
| PostgreSQL 兼容问题 | 修复 AI 上下文查询的 int32 参数溢出，改为按触发消息 seq 截止 |
| Docker 构建/迁移 | 成功；正式库到 b7a3f1e20c95 head；数据库与 API 均 healthy |
| 备份恢复 | 升级前 pg_dump 已在隔离库实际恢复，29 张 public 表；两个临时验收库均已删除 |
| 外网入口 | H5 200；健康接口正常；HTTP 308 跳 HTTPS；配对链接 302 跳 H5 配对页 |
| 实际认证/WSS | 管理员登录、资料读取、human WSS welcome/ping/pong、退出登录通过 |
| 重启 | 应用容器主动重启后重新通过健康、登录和 WSS 验证 |
| 同机服务 | Caddy 仅平滑重载；代理容器启动时间与重启次数保持原值 |

分域版本 SQLite 亦 52/52 通过，当前前端回归 8/8、类型检查及 H5 构建通过（移除了不再需要的旧地址迁移用例）。正式 API 域名带 H5 Origin 的管理员登录/资料读取、WSS 与退出通过；浏览器从 H5 跨域读取 API 健康和带 Authorization 的认证错误通过；非法来源预检 400 且无 Allow-Origin。

实际镜像 ID：`sha256:340c9a6d5d34a31bbbbc214df3bfba0534677f42ba28101551a1044d0851f64c`。

连接器 57 项和 echo E2E 的审核验证仍见 [项目审核记录](../docs/项目审核记录.md)。正式域名上线不代表真实模型供应商、Android 真机或缺失的群邀请接收 UI 已验收。

## 构建与更新

源码发布前检查本地修改，仅传源码和非秘密配置，排除 `.env`、虚拟环境、node_modules、会话、数据库及连接器凭据。更新前备份数据库与主密钥，部署后再次验证。

H5 构建（PowerShell 示例）：

```powershell
cd apps/mobile
npm ci
$env:VITE_AICHAT_SERVER='https://api.aichat.wsnbb.shop'
npm run type-check
npm run build:h5
```

将 `dist/build/h5` 内容上传到新的独立发布目录，检查后切换 `current` 链接。服务端更新：

```bash
cd /home/ubuntu/aichat/deploy
docker compose config --quiet
docker compose build server
docker compose up -d server
docker compose ps
curl -fsS https://api.aichat.wsnbb.shop/healthz
```

不要额外启动独立 worker 或多个 uvicorn worker；当前实时 hub 是进程内状态。更新前核对工作区和 `origin/main`，保留有效本地修改；工作区干净时可用 `git pull --ff-only` 同步，随后按上述命令构建和验收。

Caddy 配置更新前先验证，再平滑重载（当前镜像的 Caddy 可执行文件名为 `/service`）：

```bash
docker exec cohost-proxy-caddy-1 /service validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec cohost-proxy-caddy-1 /service reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

站点使用既有主配置的 `import /etc/caddy/Caddyfile.d/*`，无需覆盖代理部署器管理的主配置。

## 备份与回滚

本次升级前备份位于 `/home/ubuntu/aichat-backups/domain-20261026/`，目录权限 700：

- `source-before.tgz`：升级前源码，排除私有 `.env`。
- `env-before`：升级前私有配置，权限 600。
- `database-before.dump`：PostgreSQL custom 格式业务库备份，权限 600；已验证可恢复。
- Docker 保留 `aichat-server:pre-domain-20261026` 旧镜像。

发布包、校验清单和本次构建/验收日志在 `/home/ubuntu/aichat-upload/domain-20261026/`，不对 Web 开放。日志与凭据不要上传源码仓库。

分域前回滚快照在 `/home/ubuntu/aichat-backups/split-domains-20261026/`，包含数据库、私有环境、源码、Caddy 站点与旧 H5 指针；旧镜像标签为 `aichat-server:pre-split-20261026`。分域发布和 PostgreSQL 验收日志位于 `/home/ubuntu/aichat-upload/split-domains-20261026/`。拆分不迁移业务数据、不更换密码/加密密钥。

移除旧入口前的主 Caddyfile、站点与 H5 指针备份保存在 `/home/ubuntu/aichat-backups/clean-domains-20261026/`，不对外提供旧版本访问链接。当前发布校验清单位于 `/home/ubuntu/aichat-upload/clean-domains-20261026/`。

移动端三处修复发布前备份在 `/home/ubuntu/aichat-backups/mobile-fixes-20261027/`（权限 700）：`database-before.dump` 为 PostgreSQL custom 格式业务库备份，`env-before` 为私有配置（权限 600）。这次只替换 H5 静态文件，回滚无需动数据库，把 `current` 链接切回旧目录即可：

```bash
sudo ln -sfn /usr/share/caddy/aichat/releases/login-fix-20261027 /usr/share/caddy/aichat/current
```

需要回滚时先保留上线后的新增业务数据；恢复匹配的源码/Compose 与旧镜像。数据库回退应先在隔离库评估迁移与数据差异，不能直接用旧备份覆盖新数据。Fernet 主密钥须与数据库分开受控备份，不能随意轮换导致已有模型凭据无法解密。
