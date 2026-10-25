from uuid import uuid4


def new_id() -> str:
    """不透明 ID：UUID4 hex，跨模块统一使用。"""
    return uuid4().hex
