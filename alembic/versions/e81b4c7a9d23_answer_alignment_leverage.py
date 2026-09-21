"""Record how far each cell sat from the alignment's evidence

Revision ID: e81b4c7a9d23
Revises: c5d2a91f6b40
"""

import sqlalchemy as sa
from alembic import op

revision = "e81b4c7a9d23"
down_revision = "c5d2a91f6b40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, and null for every existing row: those were graded before the
    # app kept the number, and there is no way to recover it after the fact.
    # The export treats null as "unknown, include it" rather than inventing a
    # value, because excluding every historical row would empty the only
    # labelled dataset this project has.
    with op.batch_alter_table("graded_answers") as batch:
        batch.add_column(sa.Column("alignment_leverage", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("graded_answers") as batch:
        batch.drop_column("alignment_leverage")
