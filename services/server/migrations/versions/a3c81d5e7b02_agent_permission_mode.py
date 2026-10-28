"""AI 档案增加权限模式与工作目录（CLI agent 托管）

permission_mode 决定连接器以何种权限运行 CLI（plan/edit/yolo），
workspace_dir 限定 agent 的工作目录。两者放在 agent_profile 上，
重新配对不会丢失。

Revision ID: a3c81d5e7b02
Revises: b7a3f1e20c95
Create Date: 2026-10-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3c81d5e7b02'
down_revision: Union[str, None] = 'b7a3f1e20c95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agent_profile',
        sa.Column('permission_mode', sa.String(length=16), nullable=False, server_default='plan'),
    )
    op.add_column(
        'agent_profile',
        sa.Column('workspace_dir', sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('agent_profile', 'workspace_dir')
    op.drop_column('agent_profile', 'permission_mode')
