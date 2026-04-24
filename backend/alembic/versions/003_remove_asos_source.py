"""remove asos from scrapersource enum

Revision ID: 003
Revises: 002
Create Date: 2026-04-24 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL doesn't support DROP VALUE from an enum, so we rename the
    # old type, create a new one with only 'nordstrom', migrate the column,
    # then drop the old type.
    op.execute("ALTER TYPE scrapersource RENAME TO scrapersource_old")
    op.execute("CREATE TYPE scrapersource AS ENUM ('nordstrom')")
    op.execute(
        "ALTER TABLE products "
        "ALTER COLUMN source TYPE scrapersource "
        "USING source::text::scrapersource"
    )
    op.execute("DROP TYPE scrapersource_old")


def downgrade() -> None:
    op.execute("ALTER TYPE scrapersource RENAME TO scrapersource_old")
    op.execute("CREATE TYPE scrapersource AS ENUM ('asos', 'nordstrom')")
    op.execute(
        "ALTER TABLE products "
        "ALTER COLUMN source TYPE scrapersource "
        "USING source::text::scrapersource"
    )
    op.execute("DROP TYPE scrapersource_old")
