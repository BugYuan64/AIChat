# connector-runner

AIChat 外部 Agent 连接器：把任意本地 Agent（回声、OpenAI 兼容模型、未来的 CLI/SDK Agent）
通过统一协议接入 AIChat 服务。实现契约见仓库 `contracts/PROTOCOL.md`（唯一权威），
设计背景见 `docs/AI接入协议.md`。

功能：

- **配对（pair）**：RFC 8628 风格设备授权 + 本机二次确认。终端打印 ASCII 二维码与短码/确认码，
  App 扫码批准 → 本机输入 `y` 确认 → 一次性兑换凭据并写入 `0600` 权限的本地文件。
- **运行（run）**：建立连接器 WSS 会话（票据握手 → hello/welcome/ready），接收 `run.offer`
  执行任务，流式上报 `run.delta`，终态 `run.completed` / `run.failed` / `run.cancelled`；
  心跳保活，断线指数退避重连，按本地账本（sqlite3）对 `execution_id` 去重并恢复。

## 环境

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) 包管理

## 安装

```bash
cd connectors/connector-runner
uv sync            # 创建 .venv 并安装依赖（含 dev 组）
# 或者：
uv venv && uv pip install -e ".[dev]"
```

## 配对

```bash
# 环境变量方式指定服务地址（也可用 --server）
export AICHAT_SERVER_URL=https://your-aichat-server.example

uv run connector-runner pair \
  --agent-id <AI账号ID> \
  --name "办公室的 ZCode" \
  --adapter echo \
  --server https://your-aichat-server.example
```

流程：

1. 终端打印二维码（`https://<host>/pair?pid=...&code=<short_code>`，不含任何秘密）、
   短码 `short_code` 与确认码 `confirm_code`；
2. 已登录 App 扫码核对并批准 → 状态变 `pending_local`，终端展示所有者名 / AI 名 / 确认码，
   本机操作者核对后输入 `y`；
3. 兑换成功后凭据写入 `~/.aichat-connector/credentials.json`（`0600`，Windows 上尽力而为），
   `device_code` 只在创建响应出现一次，不会写日志。

所有终态（denied / expired / revoked / consumed / cancelled）都会给出明确错误并退出。

## 启动会话

```bash
uv run connector-runner run                 # 默认沿用配对时的 adapter_kind
uv run connector-runner run --adapter openai
```

前置条件：已配对（凭据文件存在）。会话行为：

- 访问令牌过期前自动用 `refresh_credential` 刷新；`401 SESSION_REVOKED` 时提示需重新配对并退出；
- 每 `heartbeat_seconds`（默认 20s）心跳；断线按 1/2/4…（最大 30s）退避重连；
- 收到 `run.offer` 先查本地账本：同 `execution_id` 已存在则不重复执行，发 `run.query` 附着原执行；
- 重连后对账本中所有未终态执行逐个 `run.query` 对账；
- `run.cancel` 尽力调用适配器 `cancel()` 后回 `run.cancelled`。

## 环境变量

| 变量 | 用途 | 默认 |
| --- | --- | --- |
| `AICHAT_SERVER_URL` | 服务地址（`--server` 优先） | 无，必填 |
| `AICHAT_CREDENTIALS_PATH` | 凭据文件路径 | `~/.aichat-connector/credentials.json` |
| `AICHAT_LEDGER_PATH` | 执行账本路径 | 与凭据同目录 `ledger.sqlite3` |
| `AICHAT_ADAPTER_API_KEY` / `OPENAI_API_KEY` | openai 适配器 API Key | 无 |
| `AICHAT_ADAPTER_BASE_URL` / `OPENAI_BASE_URL` | openai 适配器服务地址 | `https://api.openai.com/v1` |
| `AICHAT_ADAPTER_MODEL` / `OPENAI_MODEL` | openai 适配器模型名 | 无，必填 |

## 适配器扩写方法

适配器 = 实现 `connector/adapters/base.py` 的 `AgentAdapter` 协议：

```python
class AgentAdapter(Protocol):
    def run(self, context: list[dict], system_prompt: str | None) -> AsyncIterator[str]: ...
    def cancel(self) -> None: ...
```

要点：

- `run` 是**异步生成器**，每次 `yield` 一段文本（即一个 `run.delta` chunk）；
  `context` 元素形如 `{seq, sender_account_id, sender_kind, text, truncated}`；
- `cancel()` 应尽快让 `run()` 停止产出（尽力取消，不承诺外部副作用已停止）；
- 每个 Run 使用独立外部会话，不要复用全局会话，避免跨群上下文泄漏；
- 不要把群消息拼接成 shell 命令；参数、工作目录、工具权限在适配器内显式构造。

内置实现参考：`adapters/echo.py`（逐字回显，联调用）、`adapters/openai_compatible.py`
（OpenAI 兼容 chat/completions 流式）。

接入步骤：新建 `adapters/<name>.py` → 在 `adapters/__init__.py` 的 `build_adapter` 注册 →
`pair --adapter <name>` 配对（或 `run --adapter <name>` 临时切换）。

## 测试

2026-10-26 完整单元测试 57 项通过。运行时未指定服务器地址可回退至已配对凭据中的地址；进程启动先刷新保存的访问令牌。输出逐片持久化，完成后保留 `completion_pending`，断线先查询服务端并从其 next_chunk_index 重放；服务端确认终态后才结束恢复。超出字节限制的片段不发送，公开错误不包含上游异常正文。

```bash
uv run pytest            # 或：uv run python -m pytest
```

测试不依赖真实服务器：配对全流程用 `httpx.MockTransport` 假后端；账本用临时 sqlite3；
信封/状态机/回声适配器均为纯函数或纯内存测试。

## 目录结构

```text
connector-runner/
├── pyproject.toml        # uv/hatchling 包定义（依赖：httpx、websockets、qrcode、pydantic）
├── README.md
├── connector/
│   ├── __main__.py       # python -m connector
│   ├── cli.py            # argparse：pair / run
│   ├── client.py         # 统一信封 {"request_id","data"|"error"} 解析与错误码
│   ├── config.py         # ServerConfig、凭据读写（0600）、环境变量
│   ├── pairing.py        # 配对客户端：出码→轮询→本机确认→兑换
│   ├── tokens.py         # 访问令牌缓存与刷新（SESSION_REVOKED → 提示重新配对）
│   ├── ledger.py         # sqlite3 执行账本：execution_id 去重、断线恢复
│   ├── ws.py             # WSS 会话：票据握手、心跳、run.* 帧、重连恢复
│   └── adapters/         # AgentAdapter 协议 + echo / openai_compatible
└── tests/                # pytest 单元测试
```

## 安全须知

- 凭据文件含长期 `refresh_credential`，请勿提交到版本库、不要放进二维码或日志；
- `device_code`、令牌只存在本机；配对二维码只含入口 URL 与短码；
- 服务端撤销连接器后（`SESSION_REVOKED`）必须重新配对，连接器不会自动绕过。
