"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums
    scraper_source = postgresql.ENUM('asos', 'nordstrom', name='scrapersource', create_type=True)
    feedback_action = postgresql.ENUM('accepted', 'rejected', 'saved', name='feedbackaction', create_type=True)
    alert_type_enum = postgresql.ENUM('price_drop', 'restock', 'new_match', name='alerttype', create_type=True)

    scraper_source.create(op.get_bind(), checkfirst=True)
    feedback_action.create(op.get_bind(), checkfirst=True)
    alert_type_enum.create(op.get_bind(), checkfirst=True)

    # Products table
    op.create_table(
        'products',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source', sa.Enum('asos', 'nordstrom', name='scrapersource'), nullable=False),
        sa.Column('external_id', sa.String(128), nullable=False),
        sa.Column('name', sa.String(512), nullable=False),
        sa.Column('brand', sa.String(256)),
        sa.Column('url', sa.Text, nullable=False),
        sa.Column('image_url', sa.Text),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('currency', sa.String(8), default='USD'),
        sa.Column('color_name', sa.String(256)),
        sa.Column('dominant_colors', postgresql.JSON),
        sa.Column('color_match_score', sa.Integer),
        sa.Column('closest_palette_color', sa.String(16)),
        sa.Column('fabric_raw', sa.Text),
        sa.Column('fabric_parsed', postgresql.JSON),
        sa.Column('fabric_score', sa.Integer),
        sa.Column('has_excluded_fabric', sa.Boolean, default=False),
        sa.Column('description', sa.Text),
        sa.Column('available_sizes', postgresql.JSON),
        sa.Column('in_stock', sa.Boolean, default=True),
        sa.Column('is_priority_brand', sa.Boolean, default=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('scraped_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_products_source', 'products', ['source'])
    op.create_index('ix_products_external_id', 'products', ['external_id'])
    op.create_index('ix_products_brand', 'products', ['brand'])
    op.create_unique_constraint('uq_products_source_external_id', 'products', ['source', 'external_id'])

    # Matches table
    op.create_table(
        'matches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('product_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('color_score', sa.Integer, nullable=False),
        sa.Column('fabric_score', sa.Integer, nullable=False),
        sa.Column('overall_score', sa.Integer, nullable=False),
        sa.Column('is_borderline_color', sa.Boolean, default=False),
        sa.Column('claude_style_analysis', sa.Text),
        sa.Column('claude_color_reasoning', sa.Text),
        sa.Column('claude_flags', postgresql.JSON),
        sa.Column('is_new', sa.Boolean, default=True),
        sa.Column('matched_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_matches_product_id', 'matches', ['product_id'])

    # User feedback table
    op.create_table(
        'user_feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('match_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('matches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.Enum('accepted', 'rejected', 'saved', name='feedbackaction'), nullable=False),
        sa.Column('note', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_user_feedback_match_id', 'user_feedback', ['match_id'])

    # Alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('product_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('alert_type', sa.Enum('price_drop', 'restock', 'new_match', name='alerttype'), nullable=False),
        sa.Column('previous_price', sa.Float),
        sa.Column('current_price', sa.Float),
        sa.Column('message', sa.Text),
        sa.Column('is_read', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index('ix_alerts_product_id', 'alerts', ['product_id'])


def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('user_feedback')
    op.drop_table('matches')
    op.drop_table('products')

    op.execute("DROP TYPE IF EXISTS alerttype")
    op.execute("DROP TYPE IF EXISTS feedbackaction")
    op.execute("DROP TYPE IF EXISTS scrapersource")
