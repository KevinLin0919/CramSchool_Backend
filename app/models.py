"""Relational schema for the grading system.

Two rules drive most of the shape here.

First, *nothing is addressed by list position*. The service this replaces
stored a template's whole `pages` array as one JSON blob, so a question was
identified by its index; deleting one box silently renumbered every answer
after it. Questions carry a stable `question_no` instead, and it is that
number — never an offset — that pairs a student's answer to a standard one.

Second, *every write from a phone must be safe to retry*. Cram-school Wi-Fi
drops mid-upload, and a teacher's afternoon of grading cannot depend on the
network being polite. Grading sessions are keyed by a UUID the phone mints
before it ever tries to send, so a retry updates the row it created the first
time instead of inserting a duplicate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator):
    """Stores UTC, returns timezone-aware UTC, on every backend.

    SQLite has no timezone-aware type: it accepts an aware datetime and
    silently discards the offset, so a value written as +08:00 reads back
    looking like UTC. Normalising on the way in and re-attaching UTC on the way
    out makes the two backends agree, rather than differing only in the cases
    nobody tests.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, _dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, _dialect) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def _now() -> Mapped[datetime]:
    """Timestamps come from Python, not the database.

    SQLite's CURRENT_TIMESTAMP has whole-second resolution, so two edits in the
    same second produce identical `updated_at` values — and an incremental sync
    keyed on that timestamp then steps straight over one of them. Postgres has
    microseconds but stamps every row in a transaction with the transaction's
    start time, which has the same effect at a smaller scale. Generating the
    value here sidesteps both and keeps the backends behaving alike.
    """
    return mapped_column(UTCDateTime, default=utcnow, nullable=False)


# ─────────────────────────────────────────────────────────────────────────────
# 人與權限
# ─────────────────────────────────────────────────────────────────────────────


class Teacher(Base):
    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="teacher")
    created_at: Mapped[datetime] = _now()
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    tokens: Mapped[list[ApiToken]] = relationship(back_populates="teacher")

    __table_args__ = (CheckConstraint("role IN ('teacher','admin')", name="ck_teacher_role"),)

    @property
    def is_active(self) -> bool:
        return self.disabled_at is None


class ApiToken(Base):
    """One row per device, not per person.

    Only the SHA-256 of the token is stored. A stolen database therefore does
    not yield working credentials, and `revoked_at` means a teacher who leaves
    their iPad on a train is one UPDATE away from being locked out — which is
    the whole reason this is an opaque token rather than a self-contained JWT.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = _now()
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    teacher: Mapped[Teacher] = relationship(back_populates="tokens")


class InviteCode(Base):
    """Single-use code an admin hands a teacher to enrol one device."""

    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    redeemed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    teacher: Mapped[Teacher] = relationship()


# ─────────────────────────────────────────────────────────────────────────────
# 影像
# ─────────────────────────────────────────────────────────────────────────────


class Image(Base):
    """Content-addressed blob metadata; the bytes live on disk.

    Keyed by digest because the same master sheet gets re-uploaded constantly —
    every phone that syncs a template, every re-save from the web labeller. The
    client can ask `HEAD /images/sha256/{hex}` first and skip the upload
    entirely, which on a cram school's uplink is the difference between a
    template opening instantly and stalling for ten seconds.
    """

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _now()


# ─────────────────────────────────────────────────────────────────────────────
# 模板
# ─────────────────────────────────────────────────────────────────────────────


class ExamTemplate(Base):
    __tablename__ = "exam_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    exam_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Real columns, not substrings of the name. The iOS client currently infers
    # these by scanning `exam_name` for a token list, so "高一數學" classifies
    # and "數甲 L1" falls through to 其他.
    grade: Mapped[str | None] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(20))

    created_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    # Bumped on every mutation. Serves double duty: `If-Match` optimistic
    # locking so two teachers editing one template cannot silently overwrite
    # each other, and a cheap "did this change?" for clients.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Soft delete. A phone that was offline for a week has to learn that a
    # template disappeared; a hard DELETE leaves it holding a ghost forever.
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    pages: Mapped[list[TemplatePage]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplatePage.page_index",
    )

    __table_args__ = (Index("ix_templates_updated_at", "updated_at"),)

    @property
    def annotation_count(self) -> int:
        return sum(len(p.boxes) for p in self.pages)


class TemplatePage(Base):
    __tablename__ = "template_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("exam_templates.id", ondelete="CASCADE"), nullable=False
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), nullable=False)

    template: Mapped[ExamTemplate] = relationship(back_populates="pages")
    image: Mapped[Image] = relationship()
    boxes: Mapped[list[AnswerBox]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="AnswerBox.question_no",
    )

    __table_args__ = (UniqueConstraint("template_id", "page_index", name="uq_page_index"),)


class AnswerBox(Base):
    """One answer cell, in coordinates normalised against its page image.

    The old format stored these in an 800x600 "canvas" space with letterbox
    offsets baked in, which meant a bbox could not be interpreted without also
    knowing the source image's aspect ratio. Storing 0..1 fractions of the page
    makes the geometry self-describing, and the conversion both ways is exact
    (see `app/coords.py`), so nothing is lost migrating the old rows across.
    """

    __tablename__ = "answer_boxes"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("template_pages.id", ondelete="CASCADE"), nullable=False
    )
    question_no: Mapped[int] = mapped_column(Integer, nullable=False)

    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    w: Mapped[float] = mapped_column(Float, nullable=False)
    h: Mapped[float] = mapped_column(Float, nullable=False)

    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Drives which on-device recogniser runs: the MNIST CNN, the topological
    # circle/cross check, or neither.
    answer_type: Mapped[str] = mapped_column(String(16), nullable=False, default="digit")
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="答案區")

    page: Mapped[TemplatePage] = relationship(back_populates="boxes")

    __table_args__ = (
        UniqueConstraint("page_id", "question_no", name="uq_box_question_no"),
        CheckConstraint(
            "answer_type IN ('digit','mark','chinese','text')", name="ck_box_answer_type"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 學生與批改結果
# ─────────────────────────────────────────────────────────────────────────────


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    class_name: Mapped[str | None] = mapped_column(String(60))
    external_id: Mapped[str | None] = mapped_column(String(60), unique=True)
    created_at: Mapped[datetime] = _now()


class GradingSession(Base):
    """One scanned paper.

    `client_uuid` is generated on the phone and is the primary idempotency key:
    the upload endpoint is a PUT on that UUID, so a retry after a dropped
    connection overwrites rather than duplicates.
    """

    __tablename__ = "grading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_uuid: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)

    template_id: Mapped[int] = mapped_column(ForeignKey("exam_templates.id"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="SET NULL"))
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))

    # The full-page keyframe the live scan picked out.
    image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"))

    scanned_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    uploaded_at: Mapped[datetime] = _now()

    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    app_version: Mapped[str | None] = mapped_column(String(40))

    answers: Mapped[list[GradedAnswer]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="GradedAnswer.question_no",
    )

    __table_args__ = (Index("ix_sessions_scanned_at", "scanned_at"),)


class GradedAnswer(Base):
    """One question's outcome — and, when the teacher overrode it, a label.

    `teacher_value` paired with `cell_image_id` is the highest-value pair in
    this schema. Every time a teacher corrects an unsure or wrong verdict, the
    system gains one crop of real handwriting with known ground truth, produced
    as a side effect of work someone was doing anyway. Six hand-labelled cells
    is what the recogniser was tuned on; a term of ordinary use is thousands.
    """

    __tablename__ = "graded_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("grading_sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_no: Mapped[int] = mapped_column(Integer, nullable=False)

    expected: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recognized: Mapped[str | None] = mapped_column(Text)

    # Three outcomes, not two: marking a cell wrong because the model could not
    # read it blames the student for our failure.
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)

    confidence: Mapped[float | None] = mapped_column(Float)
    margin: Mapped[float | None] = mapped_column(Float)

    teacher_value: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cell_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"))

    session: Mapped[GradingSession] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_no", name="uq_answer_question_no"),
        CheckConstraint("verdict IN ('correct','wrong','unsure')", name="ck_answer_verdict"),
    )
