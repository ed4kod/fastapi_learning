"""add done_by column to tasks

Revision ID: bbacfff63bdc
Revises: f9547c6eec8e
Create Date: 2025-08-04 16:38:34.178835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bbacfff63bdc'
down_revision: Union[str, Sequence[str], None] = 'f9547c6eec8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column('title', existing_type=sa.String(), nullable=False)
        batch_op.add_column(sa.Column('done_by', sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.alter_column('title', existing_type=sa.String(), nullable=True)
        batch_op.drop_column('done_by')
