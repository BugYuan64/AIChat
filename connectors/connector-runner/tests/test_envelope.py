"""统一信封解析与错误码处理测试（契约 §0）。"""

import pytest

from connector.client import ApiError, is_throttled, parse_envelope


def test_success_returns_data():
    assert parse_envelope({"request_id": "r1", "data": {"ok": True}}) == {"ok": True}


def test_error_envelope_raises_api_error():
    payload = {
        "request_id": "r1",
        "error": {
            "code": "SLOW_DOWN",
            "message": "轮询过快",
            "retryable": True,
            "retry_after_ms": 3000,
        },
    }
    with pytest.raises(ApiError) as info:
        parse_envelope(payload, http_status=429)
    err = info.value
    assert err.code == "SLOW_DOWN"
    assert err.message == "轮询过快"
    assert err.retryable is True
    assert err.retry_after_ms == 3000
    assert err.http_status == 429
    assert "SLOW_DOWN" in str(err)


def test_error_without_optional_fields():
    with pytest.raises(ApiError) as info:
        parse_envelope({"request_id": "r1", "error": {"code": "NOT_FOUND", "message": "不存在"}})
    err = info.value
    assert err.retryable is False
    assert err.retry_after_ms is None


def test_missing_data_field_is_protocol_error():
    with pytest.raises(ApiError) as info:
        parse_envelope({"request_id": "r1"})
    assert info.value.code == "PROTOCOL_ERROR"


def test_non_dict_payload_is_protocol_error():
    with pytest.raises(ApiError):
        parse_envelope("not-a-envelope")


def test_data_not_object_is_protocol_error():
    with pytest.raises(ApiError):
        parse_envelope({"request_id": "r1", "data": [1, 2]})


@pytest.mark.parametrize(
    "code,throttled",
    [
        ("SLOW_DOWN", True),
        ("RATE_LIMITED", True),
        ("SESSION_REVOKED", False),
        ("PAIRING_CONSUMED", False),
        ("VALIDATION_FAILED", False),
    ],
)
def test_is_throttled(code, throttled):
    assert is_throttled(ApiError(code=code)) is throttled
