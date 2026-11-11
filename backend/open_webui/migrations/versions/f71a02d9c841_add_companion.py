"""Add isolated companion roles, chat switches, preferences and turn receipts."""

import sqlalchemy as sa
from alembic import op

revision = 'f71a02d9c841'
down_revision = 'e42c8f710a36'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'companion',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('persona', sa.Text(), nullable=False),
        sa.Column('model_id', sa.String(), nullable=False),
        sa.Column('state', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('target_chat_id', sa.String(), nullable=True),
        sa.Column('next_tick', sa.BigInteger(), nullable=False),
        sa.Column('lease', sa.String(), nullable=True),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_companion_user_id', 'companion', ['user_id'])
    op.create_index('ix_companion_next_tick', 'companion', ['next_tick'])
    op.create_table(
        'companion_chat',
        sa.Column('chat_id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role_id', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
    )
    op.create_index('ix_companion_chat_user_id', 'companion_chat', ['user_id'])
    op.create_table(
        'companion_preference',
        sa.Column('user_id', sa.String(), primary_key=True),
        sa.Column('data', sa.JSON(), nullable=False),
    )
    op.create_table(
        'companion_turn',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('role_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.BigInteger(), nullable=False),
    )
    op.create_index('ix_companion_turn_role_id', 'companion_turn', ['role_id'])


def downgrade():
    for table in ('companion_turn', 'companion_preference', 'companion_chat', 'companion'):
        op.drop_table(table)
