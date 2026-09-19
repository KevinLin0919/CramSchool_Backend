"""Record who last edited a template

Revision ID: c5d2a91f6b40
Revises: a3c81f4e29b7
"""

import sqlalchemy as sa
from alembic import op

revision = "c5d2a91f6b40"
down_revision = "a3c81f4e29b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode, because SQLite cannot ALTER a table to add a foreign key and
    # SQLite is what the tests and a bare `uvicorn` run use. On Postgres this
    # compiles to the plain ALTER it would have been anyway.
    #
    # Nullable, and left null for every existing row: nothing recorded who
    # edited those, and inventing an answer would be worse than admitting
    # there isn't one.
    with op.batch_alter_table("exam_templates") as batch:
        batch.add_column(sa.Column("updated_by", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_exam_templates_updated_by_teachers",
            "teachers",
            ["updated_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("exam_templates") as batch:
        batch.drop_constraint(
            "fk_exam_templates_updated_by_teachers", type_="foreignkey"
        )
        batch.drop_column("updated_by")
