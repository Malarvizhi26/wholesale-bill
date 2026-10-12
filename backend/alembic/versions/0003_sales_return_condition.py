"""sales return condition (excess vs damaged)

Revision ID: 0003_sales_return_condition
Revises: 0002_owner_pin_review_flags_rls
Create Date: 2026-10-12 14:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_sales_return_condition'
down_revision: Union[str, None] = '0002_owner_pin_review_flags_rls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('sales_return_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('return_condition', sa.String(length=20), server_default='EXCESS', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('sales_return_lines', schema=None) as batch_op:
        batch_op.drop_column('return_condition')
