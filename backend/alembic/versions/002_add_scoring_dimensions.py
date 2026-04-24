"""add scoring dimensions and auto-reject fields

Adds style_score, florida_score, auto_rejected, auto_reject_reason to matches
and color_tier to products to support the 4-component scoring system
(color 40, fabric 30, style 20, florida 10).

Revision ID: 002
Revises: 001
Create Date: 2026-04-24 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # matches — add style/florida scoring columns and auto-reject tracking
    op.add_column('matches', sa.Column('style_score', sa.Integer(), nullable=True))
    op.add_column('matches', sa.Column('florida_score', sa.Integer(), nullable=True))
    op.add_column('matches', sa.Column('auto_rejected', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('matches', sa.Column('auto_reject_reason', sa.Text(), nullable=True))

    # products — color tier classification: tier1 | tier2 | tier3 | hard_avoid | unknown
    op.add_column('products', sa.Column('color_tier', sa.String(16), nullable=True))
    op.create_index('ix_products_color_tier', 'products', ['color_tier'])


def downgrade() -> None:
    op.drop_index('ix_products_color_tier', table_name='products')
    op.drop_column('products', 'color_tier')
    op.drop_column('matches', 'auto_reject_reason')
    op.drop_column('matches', 'auto_rejected')
    op.drop_column('matches', 'florida_score')
    op.drop_column('matches', 'style_score')
