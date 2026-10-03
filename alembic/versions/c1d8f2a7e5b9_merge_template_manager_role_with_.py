"""merge template_manager role with analytics foundation

Revision ID: c1d8f2a7e5b9
Revises: a9e3d6c1f4b2, b4f1c2d3e5a6
Create Date: 2026-10-04 01:25:30.315378

The role change was cut from main so it could ship to production on its own,
while develop had already moved on with the analytics tables. Nothing to do
here beyond joining the two histories.
"""

revision = "c1d8f2a7e5b9"
down_revision = ("a9e3d6c1f4b2", "b4f1c2d3e5a6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
