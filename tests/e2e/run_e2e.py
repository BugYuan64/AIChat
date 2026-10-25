"""AIChat 端到端联调：真实 uvicorn 服务器 + 连接器（echo 适配器）+ App 模拟。

前置：
  1. services/server 已安装依赖（.venv）
  2. 已运行 bootstrap（init-db/admin/invite）
  3. 服务器已在 AICHAT_SERVER_URL 监听

运行：services/server/.venv/python tests/e2e/run_e2e.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "connectors" / "connector-runner"))

SERVER = os.environ.get("AICHAT_SERVER_URL", "http://127.0.0.1:8765")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "admin-password-123")


def unwrap(resp: httpx.Response) -> dict:
    body = resp.json()
    if "error" in body:
        raise SystemExit(f"[E2E FAIL] {resp.status_code} {body['error']}")
    return body.get("data", {})


class App:
    """App 侧最小 HTTP 客户端。"""

    def __init__(self, http: httpx.AsyncClient):
        self.http = http
        self.token: str | None = None

    async def login(self, handle: str, password: str) -> dict:
        data = unwrap(await self.http.post(f"{SERVER}/v1/auth/login",
                                           json={"handle": handle, "password": password}))
        self.token = data["access_token"]
        return data

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


async def main() -> None:
    async with httpx.AsyncClient(timeout=20) as http:
        admin = App(http)
        await admin.login("admin", ADMIN_PASSWORD)

        invites = unwrap(await http.post(f"{SERVER}/v1/admin/invites",
                                         json={"count": 2, "note": "e2e"},
                                         headers=admin.headers))["items"]
        invite_code = invites[0]["code"]

        # alice 注册登录
        alice = App(http)
        reg = unwrap(await http.post(f"{SERVER}/v1/auth/register", json={
            "invite_code": invite_code, "handle": "e2e-alice",
            "display_name": "联调用户", "password": "password-123456",
        }))
        await alice.login("e2e-alice", "password-123456")
        alice_id = reg["account_id"]
        print(f"[1] alice 就绪: {alice_id}")

        # 创建 AI
        agent = unwrap(await http.post(f"{SERVER}/v1/agents", headers=alice.headers, json={
            "handle": "e2e-ai", "display_name": "联调 AI",
        }))
        agent_id = agent["account_id"]
        print(f"[2] AI 创建: {agent_id}")

        # ---- 连接器配对（脚本扮演连接器本机的 REST 侧）----
        created = unwrap(await http.post(f"{SERVER}/v1/pairings", json={
            "agent_id": agent_id, "connector_name": "e2e-runner",
            "platform": "windows", "adapter_kind": "echo",
        }))
        print(f"[3] 配对申请: {created['pairing_id']} short_code={created['short_code']}")

        view = unwrap(await http.get(f"{SERVER}/v1/pairings/{created['pairing_id']}",
                                     params={"code": created["short_code"]},
                                     headers=alice.headers))
        assert view["confirm_code"] == created["confirm_code"], "确认码两端不一致"
        unwrap(await http.post(f"{SERVER}/v1/pairings/{created['pairing_id']}/decision",
                               json={"decision": "approve", "confirm_code": created["confirm_code"],
                                     "expected_version": 1},
                               headers=alice.headers))
        status = unwrap(await http.post(f"{SERVER}/v1/pairing-status",
                                        json={"device_code": created["device_code"]}))
        assert status["status"] == "pending_local" and status["owner_display_name"] == "联调用户"
        unwrap(await http.post(f"{SERVER}/v1/pairing-local-confirmation",
                               json={"device_code": created["device_code"], "confirmed": True}))
        tokens = unwrap(await http.post(f"{SERVER}/v1/pairing-token",
                                        json={"device_code": created["device_code"]}))
        print(f"[4] 配对兑换成功: connector={tokens['connector_id']}")

        # ---- 授权 + 私聊 ----
        req = unwrap(await http.post(f"{SERVER}/v1/contact-requests",
                                     json={"target_account_id": agent_id}, headers=alice.headers))
        unwrap(await http.post(f"{SERVER}/v1/contact-requests/{req['request_id']}/decision",
                               json={"decision": "accept"}, headers=alice.headers))
        direct = unwrap(await http.post(f"{SERVER}/v1/conversations/direct",
                                        json={"target_account_id": agent_id}, headers=alice.headers))
        conv_id = direct["conversation_id"]
        print(f"[5] 私聊就绪: {conv_id}")

        # ---- 启动真实连接器会话（echo 适配器）----
        from connector.adapters import build_adapter
        from connector.config import ServerConfig
        from connector.ledger import Ledger
        from connector.tokens import TokenManager
        from connector.ws import ConnectorSession

        tmp = ROOT / "tests" / "e2e" / ".tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        credentials = {
            "connector_id": tokens["connector_id"],
            "agent_id": tokens["agent_id"],
            "access_token": tokens["access_token"],
            "refresh_credential": tokens["refresh_credential"],
            "expires_in": tokens["expires_in"],
            "server_base_url": SERVER,
            "adapter_kind": "echo",
        }
        config = ServerConfig(server_base_url=SERVER,
                              credentials_path=tmp / "credentials.json",
                              ledger_path=tmp / "ledger.sqlite3")
        token_manager = TokenManager(credentials, SERVER, http)
        ledger = Ledger(config.ledger_path)
        adapter = build_adapter("echo")
        session = ConnectorSession(config=config, token_manager=token_manager, ledger=ledger,
                                   adapter=adapter, http=http, adapter_kind="echo",
                                   connector_id=tokens["connector_id"])
        session_task = asyncio.create_task(session.run_forever())
        await asyncio.sleep(3)  # 等握手 + ready
        print("[6] 连接器会话已启动")

        # ---- 发消息并等待 AI 流式回复 ----
        trigger_text = "你好连接器，这是端到端消息"
        sent = unwrap(await http.post(f"{SERVER}/v1/conversations/{conv_id}/messages",
                                      json={"client_message_id": f"e2e-{int(time.time())}",
                                            "text": trigger_text},
                                      headers=alice.headers))
        assert sent["runs"], "应创建 Run"
        run_id = sent["runs"][0]["run_id"]
        print(f"[7] 消息已发送，run={run_id}（state={sent['runs'][0]['state']}）")

        deadline = time.time() + 30
        final_message = None
        while time.time() < deadline:
            await asyncio.sleep(0.5)
            history = unwrap(await http.get(f"{SERVER}/v1/conversations/{conv_id}/messages",
                                            headers=alice.headers))
            for item in history["items"]:
                if item.get("run_id") == run_id and item["status"] == "final":
                    final_message = item
                    break
            if final_message:
                break
        assert final_message is not None, "超时：AI 未完成回复"
        assert trigger_text in final_message["text"], f"echo 内容异常: {final_message['text'][:80]}"
        print(f"[8] AI 回复完成（final, {len(final_message['text'])} 字符）")

        run_view = unwrap(await http.get(f"{SERVER}/v1/runs/{run_id}", headers=alice.headers))
        assert run_view["state"] == "succeeded"
        print(f"[9] run 终态: {run_view['state']}")

        # ---- 事件补拉 ----
        await asyncio.sleep(2)  # 等扇出
        events = unwrap(await http.get(f"{SERVER}/v1/events", params={"after": "0"},
                                       headers=alice.headers))
        types = [i["type"] for i in events["items"]]
        assert "message.created" in types and "run.updated" in types, f"事件缺失: {types}"
        print(f"[10] 事件补拉 OK（{len(types)} 条，cursor={events['next_cursor']}）")

        session_task.cancel()
        print("\n=== E2E 全链路通过：配对 → 授权 → 私聊 → 连接器执行 → 流式回复 → 事件 ===")


if __name__ == "__main__":
    asyncio.run(main())
