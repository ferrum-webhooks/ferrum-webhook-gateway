"""add traceparent to deliveries and outbox

Revision ID: 5d9e3f7a2c84
Revises: 3b7c1d9e5a42
Create Date: 2026-10-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5d9e3f7a2c84'
down_revision: Union[str, Sequence[str], None] = '3b7c1d9e5a42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deliveries', sa.Column('traceparent', sa.String(), nullable=True))
    op.add_column('outbox', sa.Column('traceparent', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('outbox', 'traceparent')
    op.drop_column('deliveries', 'traceparent')
