"""streams, outbox, idempotency, signing secrets

Revision ID: 3b7c1d9e5a42
Revises: 0f453657c9d3
Create Date: 2026-10-08 12:00:00.000000

Legacy data note: deliveries used to be one row per *attempt*. They are now one row
per (event, webhook) with attempts in delivery_attempts, so legacy duplicates are
collapsed to the latest row (per-attempt history of pre-migration deliveries is dropped).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3b7c1d9e5a42'
down_revision: Union[str, Sequence[str], None] = '0f453657c9d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- webhooks: signing secret -------------------------------------------------
    op.add_column('webhooks', sa.Column('secret', sa.String(), nullable=True))
    op.add_column('webhooks', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE webhooks SET secret = 'whsec_' || "
        "encode(decode(md5(random()::text || id::text) || md5(random()::text), 'hex'), 'base64') "
        "WHERE secret IS NULL"
    )
    op.create_index(op.f('ix_webhooks_user_id'), 'webhooks', ['user_id'], unique=False)

    # --- events: stable public id + idempotency key --------------------------------
    op.add_column('events', sa.Column('public_id', sa.String(), nullable=True))
    op.add_column('events', sa.Column('idempotency_key', sa.String(), nullable=True))
    op.execute(
        "UPDATE events SET public_id = 'evt_' || md5(random()::text || id::text) "
        "WHERE public_id IS NULL"
    )
    op.create_index(op.f('ix_events_public_id'), 'events', ['public_id'], unique=True)
    op.create_index(op.f('ix_events_user_id'), 'events', ['user_id'], unique=False)
    op.create_unique_constraint(
        'uq_events_user_idempotency', 'events', ['user_id', 'idempotency_key']
    )

    # --- deliveries: one row per (event, webhook) -------------------------------------
    op.execute(
        "DELETE FROM deliveries d USING deliveries newer "
        "WHERE d.event_id = newer.event_id AND d.webhook_id = newer.webhook_id AND d.id < newer.id"
    )
    op.add_column('deliveries', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_deliveries_event_id'), 'deliveries', ['event_id'], unique=False)
    op.create_index('ix_deliveries_due', 'deliveries', ['status', 'next_retry_at'], unique=False)
    op.create_unique_constraint(
        'uq_deliveries_event_webhook', 'deliveries', ['event_id', 'webhook_id']
    )

    op.create_table(
        'delivery_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('delivery_id', sa.Integer(), nullable=False),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['delivery_id'], ['deliveries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_delivery_attempts_id'), 'delivery_attempts', ['id'], unique=False)
    op.create_index(op.f('ix_delivery_attempts_delivery_id'), 'delivery_attempts', ['delivery_id'], unique=False)

    # --- transactional outbox ------------------------------------------------------------
    op.create_table(
        'outbox',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('delivery_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['delivery_id'], ['deliveries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_outbox_id'), 'outbox', ['id'], unique=False)
    op.create_index('ix_outbox_unpublished', 'outbox', ['published_at', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_outbox_unpublished', table_name='outbox')
    op.drop_index(op.f('ix_outbox_id'), table_name='outbox')
    op.drop_table('outbox')
    op.drop_index(op.f('ix_delivery_attempts_delivery_id'), table_name='delivery_attempts')
    op.drop_index(op.f('ix_delivery_attempts_id'), table_name='delivery_attempts')
    op.drop_table('delivery_attempts')
    op.drop_constraint('uq_deliveries_event_webhook', 'deliveries', type_='unique')
    op.drop_index('ix_deliveries_due', table_name='deliveries')
    op.drop_index(op.f('ix_deliveries_event_id'), table_name='deliveries')
    op.drop_column('deliveries', 'locked_until')
    op.drop_constraint('uq_events_user_idempotency', 'events', type_='unique')
    op.drop_index(op.f('ix_events_user_id'), table_name='events')
    op.drop_index(op.f('ix_events_public_id'), table_name='events')
    op.drop_column('events', 'idempotency_key')
    op.drop_column('events', 'public_id')
    op.drop_index(op.f('ix_webhooks_user_id'), table_name='webhooks')
    op.drop_column('webhooks', 'deleted_at')
    op.drop_column('webhooks', 'secret')
