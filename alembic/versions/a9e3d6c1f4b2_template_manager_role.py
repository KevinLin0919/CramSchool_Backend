"""teacher role: template_manager

Revision ID: a9e3d6c1f4b2
Revises: e81b4c7a9d23
Create Date: 2026-10-04 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "a9e3d6c1f4b2"
down_revision = "e81b4c7a9d23"
branch_labels = None
depends_on = None

_OLD = "role IN ('teacher','admin')"
_NEW = "role IN ('teacher','template_manager','admin')"


def upgrade() -> None:
    # batch mode because SQLite cannot alter a CHECK constraint in place.
    with op.batch_alter_table("teachers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_teacher_role", type_="check")
        batch_op.create_check_constraint("ck_teacher_role", sa.text(_NEW))


def downgrade() -> None:
    # A template manager goes back to an ordinary teacher, the role this one
    # was carved out of, rather than blocking the downgrade on data it created.
    op.execute("UPDATE teachers SET role = 'teacher' WHERE role = 'template_manager'")
    with op.batch_alter_table("teachers", schema=None) as batch_op:
        batch_op.drop_constraint("ck_teacher_role", type_="check")
        batch_op.create_check_constraint("ck_teacher_role", sa.text(_OLD))
