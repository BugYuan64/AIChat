"""本地执行账本（sqlite3）：按 execution_id 去重、断线重连恢复依据。

两张表：
- executions：execution_id 主键、run_id、status、chunks（JSON 数组）、final_text、
  updated_at，另存 attempt_no / fencing_token 便于审计。
- sessions：外部 Agent 的会话索引。CLI 的会话状态活在它自己那边（磁盘或守护进程），
  账本只记"这个对话该用哪个 session id 续接"。没有它，连接器一重启就丢失上下文线索。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Run 终态（契约 §8）：进入终态后不再参与恢复
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled", "expired")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS executions (
    execution_id  TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    status        TEXT NOT NULL,
    chunks        TEXT NOT NULL DEFAULT '[]',
    final_text    TEXT,
    updated_at    TEXT NOT NULL,
    attempt_no    INTEGER,
    fencing_token TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    session_key         TEXT NOT NULL,
    adapter_kind        TEXT NOT NULL,
    external_session_id TEXT,
    cwd                 TEXT,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (session_key, adapter_kind)
);
"""


@dataclass(frozen=True)
class ExecutionRecord:
    execution_id: str
    run_id: str
    status: str
    chunks: list[str]
    final_text: str | None
    updated_at: str
    attempt_no: int | str | None = None
    fencing_token: str | int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES


def _row_to_record(row: sqlite3.Row) -> ExecutionRecord:
    try:
        chunks = json.loads(row["chunks"] or "[]")
    except json.JSONDecodeError:
        chunks = []
    return ExecutionRecord(
        execution_id=row["execution_id"],
        run_id=row["run_id"],
        status=row["status"],
        chunks=chunks if isinstance(chunks, list) else [],
        final_text=row["final_text"],
        updated_at=row["updated_at"],
        attempt_no=row["attempt_no"],
        fencing_token=row["fencing_token"],
    )


@dataclass(frozen=True)
class SessionRecord:
    """一条外部 Agent 会话索引。external_session_id 为 None 表示尚未建立会话。"""

    session_key: str
    adapter_kind: str
    external_session_id: str | None
    cwd: str | None
    updated_at: str


def _row_to_session(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        session_key=row["session_key"],
        adapter_kind=row["adapter_kind"],
        external_session_id=row["external_session_id"],
        cwd=row["cwd"],
        updated_at=row["updated_at"],
    )


class Ledger:
    """sqlite3 账本；单事件循环内同步使用即可。"""

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def get(self, execution_id: str) -> ExecutionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        return _row_to_record(row) if row is not None else None

    def upsert(
        self,
        execution_id: str,
        *,
        run_id: str | None = None,
        status: str | None = None,
        chunks: list[str] | None = None,
        final_text: str | None = None,
        attempt_no: int | str | None = None,
        fencing_token: int | str | None = None,
    ) -> None:
        """插入或部分更新：None 字段保持原值；新建必须提供 run_id。

        同一 execution_id 重复插入不会产生第二行（主键去重，run.offer 重放场景）。
        """
        existing = self.get(execution_id)
        if existing is None and not run_id:
            raise ValueError(f"新建执行记录 {execution_id!r} 必须提供 run_id")
        effective_run_id = run_id if run_id is not None else (existing.run_id if existing else "")
        effective_status = status if status is not None else (existing.status if existing else "unknown")
        effective_chunks = chunks if chunks is not None else (existing.chunks if existing else [])
        effective_final = final_text if final_text is not None else (existing.final_text if existing else None)
        effective_attempt = (
            attempt_no if attempt_no is not None else (existing.attempt_no if existing else None)
        )
        effective_fence = (
            fencing_token
            if fencing_token is not None
            else (existing.fencing_token if existing else None)
        )
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO executions
                    (execution_id, run_id, status, chunks, final_text, updated_at, attempt_no, fencing_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    effective_run_id,
                    effective_status,
                    json.dumps(effective_chunks, ensure_ascii=False),
                    effective_final,
                    datetime.now(timezone.utc).isoformat(),
                    effective_attempt,
                    str(effective_fence) if effective_fence is not None else None,
                ),
            )

    def list_unfinished(self) -> list[ExecutionRecord]:
        """所有未终态执行：断线重连后逐个 run.query。"""
        placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
        rows = self._conn.execute(
            f"SELECT * FROM executions WHERE status NOT IN ({placeholders}) ORDER BY updated_at",
            TERMINAL_STATUSES,
        ).fetchall()
        return [_row_to_record(r) for r in rows]

    def list_all(self) -> list[ExecutionRecord]:
        rows = self._conn.execute("SELECT * FROM executions ORDER BY updated_at").fetchall()
        return [_row_to_record(r) for r in rows]

    # ---- 外部会索引 ----

    def get_session(self, session_key: str, adapter_kind: str) -> SessionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_key = ? AND adapter_kind = ?",
            (session_key, adapter_kind),
        ).fetchone()
        return _row_to_session(row) if row is not None else None

    def save_session(
        self,
        session_key: str,
        adapter_kind: str,
        *,
        external_session_id: str | None = None,
        cwd: str | None = None,
    ) -> None:
        """记录/更新会话索引；外部 session id 为 None 时不覆盖已有值。"""
        existing = self.get_session(session_key, adapter_kind)
        effective_id = (
            external_session_id
            if external_session_id is not None
            else (existing.external_session_id if existing else None)
        )
        effective_cwd = cwd if cwd is not None else (existing.cwd if existing else None)
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO sessions
                    (session_key, adapter_kind, external_session_id, cwd, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_key,
                    adapter_kind,
                    effective_id,
                    effective_cwd,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def clear_session(self, session_key: str, adapter_kind: str) -> None:
        """丢弃失效会话（如 --resume 失败），下次运行会新建。"""
        with self._conn:
            self._conn.execute(
                "DELETE FROM sessions WHERE session_key = ? AND adapter_kind = ?",
                (session_key, adapter_kind),
            )

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Ledger":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
