"""本地执行账本测试：execution_id 去重、部分更新、未终态恢复列表。"""

import pytest

from connector.ledger import Ledger


@pytest.fixture()
def ledger(tmp_path):
    with Ledger(tmp_path / "ledger.sqlite3") as led:
        yield led


def test_upsert_and_get(ledger):
    ledger.upsert("e1", run_id="r1", status="accepted", attempt_no=1, fencing_token="f1")
    rec = ledger.get("e1")
    assert rec is not None
    assert rec.run_id == "r1"
    assert rec.status == "accepted"
    assert rec.chunks == []
    assert rec.final_text is None
    assert rec.attempt_no == 1
    assert rec.fencing_token == "f1"
    assert not rec.is_terminal


def test_get_missing_returns_none(ledger):
    assert ledger.get("nope") is None


def test_create_requires_run_id(ledger):
    with pytest.raises(ValueError):
        ledger.upsert("e1", status="accepted")


def test_update_preserves_untouched_fields(ledger):
    ledger.upsert("e1", run_id="r1", status="running", attempt_no=2)
    ledger.upsert("e1", status="succeeded", chunks=["你好", "世界"], final_text="你好世界")
    rec = ledger.get("e1")
    assert rec.run_id == "r1"  # 未传 run_id 保持原值
    assert rec.status == "succeeded"
    assert rec.chunks == ["你好", "世界"]
    assert rec.final_text == "你好世界"
    assert rec.attempt_no == 2
    assert rec.is_terminal


def test_upsert_same_execution_id_deduplicates(ledger):
    """同 execution_id 反复 upsert 只有一行（run.offer 重放去重依据）。"""
    ledger.upsert("e1", run_id="r1", status="accepted")
    ledger.upsert("e1", run_id="r1", status="running")
    ledger.upsert("e1", run_id="r1", status="succeeded", final_text="done")
    assert len(ledger.list_all()) == 1
    assert ledger.get("e1").status == "succeeded"


def test_list_unfinished_excludes_terminal(ledger):
    ledger.upsert("e1", run_id="r1", status="running")
    ledger.upsert("e2", run_id="r2", status="accepted")
    ledger.upsert("e3", run_id="r3", status="succeeded", final_text="ok")
    ledger.upsert("e4", run_id="r4", status="failed")
    ledger.upsert("e5", run_id="r5", status="cancelled")
    unfinished = {rec.execution_id for rec in ledger.list_unfinished()}
    assert unfinished == {"e1", "e2"}


def test_persistence_across_reopen(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    with Ledger(path) as led:
        led.upsert("e1", run_id="r1", status="running", chunks=["a"])
    with Ledger(path) as led:
        rec = led.get("e1")
        assert rec.status == "running"
        assert rec.chunks == ["a"]
