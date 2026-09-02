"""answer_type: choice

Revision ID: a3c81f4e29b7
Revises: f70a334a550c
Create Date: 2026-09-02 10:12:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a3c81f4e29b7'
down_revision = 'f70a334a550c'
branch_labels = None
depends_on = None

_OLD = "answer_type IN ('digit','mark','chinese','text')"
_NEW = "answer_type IN ('digit','mark','chinese','text','choice')"


def upgrade() -> None:
    # batch mode because SQLite — which is what development runs on — cannot
    # alter a CHECK constraint in place. Without it this passes in production
    # and fails only on the machine nobody deploys from, which is the hardest
    # way round for a migration to break.
    with op.batch_alter_table('answer_boxes', schema=None) as batch_op:
        batch_op.drop_constraint('ck_box_answer_type', type_='check')
        batch_op.create_check_constraint('ck_box_answer_type', sa.text(_NEW))


def downgrade() -> None:
    # Anything already marked `choice` would violate the old constraint, so it
    # goes back to the value it was widened from rather than blocking the
    # downgrade on data this migration created.
    op.execute("UPDATE answer_boxes SET answer_type = 'digit' WHERE answer_type = 'choice'")
    with op.batch_alter_table('answer_boxes', schema=None) as batch_op:
        batch_op.drop_constraint('ck_box_answer_type', type_='check')
        batch_op.create_check_constraint('ck_box_answer_type', sa.text(_OLD))
