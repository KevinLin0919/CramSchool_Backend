"""Classes, exams and the answer snapshots analysis reads

Revision ID: b4f1c2d3e5a6
Revises: e81b4c7a9d23
"""

import re
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "b4f1c2d3e5a6"
down_revision = "e81b4c7a9d23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(),
                  sa.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("class_id", sa.Integer(),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", sa.Integer(),
                  sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("class_id", "student_id", name="uq_enrollment"),
    )
    op.create_table(
        "exams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_uuid", sa.Uuid(), nullable=False, unique=True),
        sa.Column("teacher_id", sa.Integer(),
                  sa.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("class_id", sa.Integer(),
                  sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(),
                  sa.ForeignKey("exam_templates.id"), nullable=False),
        sa.Column("exam_date", sa.Date(), nullable=False),
        sa.Column("sitting", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("teacher_id", "class_id", "template_id", "exam_date", "sitting",
                            name="uq_exam_sitting"),
    )
    op.create_table(
        "web_login_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(),
                  sa.ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "insight_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("teacher_id", sa.Integer(),
                  sa.ForeignKey("teachers.id", ondelete="SET NULL")),
        sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("cache_key", sa.String(64), index=True),
        sa.Column("question", sa.Text()),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("model", sa.String(80)),
        sa.Column("tool_log", sa.Text()),
        sa.Column("answer", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('pending','running','done','failed')",
                           name="ck_insight_status"),
    )

    # Every new column is nullable or defaulted: rows written by today's app,
    # and by the phones teachers already have, must keep going in unchanged.
    with op.batch_alter_table("api_tokens") as batch:
        batch.add_column(sa.Column("kind", sa.String(10), nullable=False,
                                   server_default="device"))
        batch.create_check_constraint("ck_token_kind", "kind IN ('device','web')")

    with op.batch_alter_table("exam_templates") as batch:
        batch.add_column(sa.Column("unit", sa.String(40)))
        batch.add_column(sa.Column("option_count", sa.Integer(), nullable=False,
                                   server_default="4"))
        batch.add_column(sa.Column("name_page_index", sa.Integer()))
        for col in ("name_x", "name_y", "name_w", "name_h"):
            batch.add_column(sa.Column(col, sa.Float()))

    with op.batch_alter_table("grading_sessions") as batch:
        batch.add_column(sa.Column("exam_id", sa.Integer()))
        batch.add_column(sa.Column("identity_source", sa.String(12)))
        batch.add_column(sa.Column("identified_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("name_image_id", sa.Integer()))
        batch.create_foreign_key("fk_sessions_exam", "exams", ["exam_id"], ["id"],
                                 ondelete="SET NULL")
        batch.create_foreign_key("fk_sessions_name_image", "images", ["name_image_id"], ["id"])

    with op.batch_alter_table("graded_answers") as batch:
        batch.add_column(sa.Column("answer_type", sa.String(16)))
        batch.add_column(sa.Column("chosen", sa.String(32)))

    _backfill()


def _backfill() -> None:
    """Units from existing names, and snapshots for answers already stored.

    Parsing the name is acceptable exactly once, here, for the handful of
    templates that predate the column; after this a unit is typed, not guessed.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.grading import chosen  # noqa: PLC0415

    bind = op.get_bind()
    for tid, name in bind.execute(sa.text("SELECT id, exam_name FROM exam_templates")):
        match = re.search(r"\d+-\d+", name or "")
        if match:
            bind.execute(sa.text("UPDATE exam_templates SET unit = :u WHERE id = :i"),
                         {"u": match.group(0), "i": tid})

    boxes = {}
    for tid, qno, atype, count in bind.execute(sa.text(
        "SELECT p.template_id, b.question_no, b.answer_type, t.option_count "
        "FROM answer_boxes b JOIN template_pages p ON p.id = b.page_id "
        "JOIN exam_templates t ON t.id = p.template_id"
    )):
        boxes.setdefault((tid, qno), (atype, count))

    rows = bind.execute(sa.text(
        "SELECT a.id, s.template_id, a.question_no, a.teacher_value, a.recognized, a.verdict "
        "FROM graded_answers a JOIN grading_sessions s ON s.id = a.session_id"
    )).all()
    for aid, tid, qno, tv, rec, verdict in rows:
        atype, count = boxes.get((tid, qno), (None, 4))
        bind.execute(
            sa.text("UPDATE graded_answers SET answer_type = :t, chosen = :c WHERE id = :i"),
            {"t": atype, "c": chosen(tv, rec, verdict, atype, count), "i": aid},
        )


def downgrade() -> None:
    with op.batch_alter_table("graded_answers") as batch:
        batch.drop_column("chosen")
        batch.drop_column("answer_type")
    with op.batch_alter_table("grading_sessions") as batch:
        batch.drop_constraint("fk_sessions_name_image", type_="foreignkey")
        batch.drop_constraint("fk_sessions_exam", type_="foreignkey")
        for col in ("name_image_id", "identified_at", "identity_source", "exam_id"):
            batch.drop_column(col)
    with op.batch_alter_table("exam_templates") as batch:
        for col in ("name_h", "name_w", "name_y", "name_x", "name_page_index",
                    "option_count", "unit"):
            batch.drop_column(col)
    with op.batch_alter_table("api_tokens") as batch:
        batch.drop_constraint("ck_token_kind", type_="check")
        batch.drop_column("kind")
    op.drop_table("insight_runs")
    op.drop_table("web_login_codes")
    op.drop_table("exams")
    op.drop_table("enrollments")
    op.drop_table("classes")
