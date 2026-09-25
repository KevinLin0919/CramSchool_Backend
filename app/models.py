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
from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
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

    # Entra's stable object id for this person. Identity is keyed on this
    # rather than on the email address, because addresses change — someone
    # marries, an account is renamed — and a teacher whose key changed would
    # come back as a new person with none of their grading history.
    microsoft_oid: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = _now()
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    tokens: Mapped[list[ApiToken]] = relationship(back_populates="teacher")

    __table_args__ = (
        CheckConstraint("role IN ('teacher','admin')", name="ck_teacher_role"),
        UniqueConstraint("microsoft_oid", name="uq_teacher_microsoft_oid"),
    )

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
    # `device` for the phone, `web` for a browser signed in with a one-time
    # code from it. Kept apart because they deserve different lifetimes: a
    # browser on a shared school computer should not hold a month-long key.
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="device")

    teacher: Mapped[Teacher] = relationship(back_populates="tokens")

    __table_args__ = (CheckConstraint("kind IN ('device','web')", name="ck_token_kind"),)


class WebLoginCode(Base):
    """Six digits the phone shows so a browser can sign in as the same teacher.

    Six digits is a small space, which is why everything else about it is
    short: three minutes, one use, a handful of wrong guesses, and at most one
    live code per teacher. Stored hashed like every other credential here.
    """

    __tablename__ = "web_login_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


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
    # The unit this paper covers ("1-1", "1-2"…), which is what progress is
    # tracked across. A column like grade and subject, not parsed out of the
    # name, because names are written by people.
    unit: Mapped[str | None] = mapped_column(String(40))
    # How many options a multiple-choice question offers. Needed to say an
    # option nobody chose exists at all — the answer key alone cannot, when no
    # question's answer happens to be 4.
    option_count: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    # Where students write their name, as a fraction of one page. On the
    # template rather than the page because pages are rebuilt wholesale on
    # every edit, and a name box stored there would vanish the first time a
    # teacher fixed an answer. Null for papers without a name field.
    name_page_index: Mapped[int | None] = mapped_column(Integer)
    name_x: Mapped[float | None] = mapped_column(Float)
    name_y: Mapped[float | None] = mapped_column(Float)
    name_w: Mapped[float | None] = mapped_column(Float)
    name_h: Mapped[float | None] = mapped_column(Float)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))
    # Who last changed it, which `created_by` cannot answer.
    #
    # Editing a template means editing an answer key, and that is the one
    # change here with no visible symptom: nothing breaks, every paper graded
    # afterwards is simply wrong, for the whole class. Without this the
    # question "who set question 7 to 0, and when" has no answer at all —
    # `created_by` is written once and never touched again.
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))
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
            "answer_type IN ('digit','mark','chinese','text','choice')",
            name="ck_box_answer_type",
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


class SchoolClass(Base):
    """A teacher's class, and the only thing that makes a student theirs.

    Students are shared rows (a child can be in two teachers' classes); what a
    teacher may see or assign is decided by enrolment in a class they own.
    """

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"),
                                            nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    # Demo data lives in the same database as the real thing, under the same
    # teacher, so this is what keeps it apart — and what one command deletes.
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _now()

    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="school_class", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"),
                                          nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"),
                                            nullable=False)

    school_class: Mapped[SchoolClass] = relationship(back_populates="enrollments")
    student: Mapped[Student] = relationship()

    __table_args__ = (UniqueConstraint("class_id", "student_id", name="uq_enrollment"),)


class Exam(Base):
    """One sitting: a class, a paper, a day. What the app calls a stack.

    Keyed by a UUID the phone mints, like a grading session, so a stack can be
    started and filled with no network at all. The date is the Taipei calendar
    day the phone saw, not a UTC timestamp: a paper graded at 7am belongs to
    today, not to yesterday.
    """

    __tablename__ = "exams"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_uuid: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"),
                                            nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"),
                                          nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("exam_templates.id"), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    # A second sitting of the same paper on the same day — a retake — is a
    # separate exam, not more papers on the first one.
    sitting: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = _now()

    school_class: Mapped[SchoolClass] = relationship()
    template: Mapped[ExamTemplate] = relationship()

    __table_args__ = (
        UniqueConstraint("teacher_id", "class_id", "template_id", "exam_date", "sitting",
                         name="uq_exam_sitting"),
    )


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

    # Which sitting and which child. Set through their own endpoint and never
    # by the upload PUT: the upload is resent in full after every correction,
    # and an app that does not know these fields would otherwise erase them.
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id", ondelete="SET NULL"))
    # How the student was decided: `teacher` (picked from the roster) or
    # `suggested` (a suggestion the teacher accepted). Never set without a
    # teacher having confirmed it.
    identity_source: Mapped[str | None] = mapped_column(String(12))
    identified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    name_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"))

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
    # How far this cell sat from the evidence the alignment was fitted to, on
    # the frame its crop was taken from.
    #
    # Sent by the app because a person cannot see it. A box that drifted onto
    # blank paper and a cell the student left empty are the same picture, and
    # the export below needs to tell them apart: a crop of the wrong part of
    # the page carries a label that teaches the recogniser nothing.
    alignment_leverage: Mapped[float | None] = mapped_column(Float)

    # Three outcomes, not two: marking a cell wrong because the model could not
    # read it blames the student for our failure.
    verdict: Mapped[str] = mapped_column(String(10), nullable=False)

    confidence: Mapped[float | None] = mapped_column(Float)
    margin: Mapped[float | None] = mapped_column(Float)

    teacher_value: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cell_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"))

    # Snapshots taken on the server at upload, so analysis never has to ask a
    # template that may have changed since. `chosen` is what the student
    # answered in canonical form (the teacher's reading if there is one), or
    # null when nothing usable was read. See `app/grading.py`.
    answer_type: Mapped[str | None] = mapped_column(String(16))
    chosen: Mapped[str | None] = mapped_column(String(32))

    session: Mapped[GradingSession] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_no", name="uq_answer_question_no"),
        CheckConstraint("verdict IN ('correct','wrong','unsure')", name="ck_answer_verdict"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# AI
# ─────────────────────────────────────────────────────────────────────────────


class InsightRun(Base):
    """One question put to the model, and everything needed to audit it.

    Stored whether it succeeded or not: which tools it called and what they
    returned is how a wrong answer gets traced, and the token counts are how
    the monthly bill gets explained.
    """

    __tablename__ = "insight_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.id", ondelete="SET NULL"))
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # Cache key: the same question about the same data is answered once.
    cache_key: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    model: Mapped[str | None] = mapped_column(String(80))
    tool_log: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    __table_args__ = (
        CheckConstraint("status IN ('pending','running','done','failed')",
                        name="ck_insight_status"),
    )
