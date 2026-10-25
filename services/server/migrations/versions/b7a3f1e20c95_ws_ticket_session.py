"""ws_ticket 绑定登录会话：撤销会话即时断开对应 WSS 连接

Revision ID: b7a3f1e20c95
Revises: c5960d029b28
Create Date: 2026-10-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7a3f1e20c95'
down_revision: Union[str, None] = 'c5960d029b28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ws_ticket', sa.Column('session_id', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('ws_ticket', 'session_id')
