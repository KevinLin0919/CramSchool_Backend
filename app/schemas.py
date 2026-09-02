"""Request/response contracts.

These are the OpenAPI schema, so they are also what a generated Swift client
gets. Validation lives here rather than in the handlers: the service this
replaces checked `data.get("pages")` by hand and returned a different error
shape from each endpoint, which the iOS client papered over with three
successive `??` fallbacks when parsing detection results.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# `choice` is `digit` with an arity: exactly one character, because the cell is
# a multiple-choice answer and cannot hold more. It is a separate value rather
# than a flag because it is the template that knows this, and the device should
# be told rather than left to infer it from the answer key's own shape.
AnswerType = Literal["digit", "mark", "chinese", "text", "choice"]
Verdict = Literal["correct", "wrong", "unsure"]

# 0..1 with a little slack: a labeller can legitimately drag a box a hair past
# the page edge, and rejecting that would fail a save for a rounding artefact.
Fraction = Annotated[float, Field(ge=-0.05, le=1.05)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── 認證 ─────────────────────────────────────────────────────────────────────


class TokenRequest(BaseModel):
    invite_code: str = Field(min_length=6, max_length=128)
    device_name: str | None = Field(default=None, max_length=120)


class MicrosoftTokenRequest(BaseModel):
    """The ID token from the tenant, straight from the sign-in flow.

    No access token and no authorization code: this service only needs to know
    *who* signed in, and asking for anything that could act on their behalf
    would be collecting a capability it has no use for.
    """

    id_token: str = Field(min_length=32, max_length=8192)
    device_name: str | None = Field(default=None, max_length=120)


class TokenResponse(BaseModel):
    token: str
    teacher_id: int
    teacher_name: str
    role: str
    expires_at: datetime | None


class TeacherOut(ORMModel):
    id: int
    name: str
    email: str | None
    role: str


# ── 影像 ─────────────────────────────────────────────────────────────────────


class ImageOut(ORMModel):
    id: int
    sha256: str
    mime: str
    width: int
    height: int
    bytes: int


# ── 模板 ─────────────────────────────────────────────────────────────────────


class AnswerBoxIn(BaseModel):
    question_no: int = Field(ge=1)
    x: Fraction
    y: Fraction
    w: Annotated[float, Field(gt=0, le=1.1)]
    h: Annotated[float, Field(gt=0, le=1.1)]
    answer: str = ""
    answer_type: AnswerType = "digit"
    label: str = "答案區"


class AnswerBoxOut(ORMModel):
    question_no: int
    x: float
    y: float
    w: float
    h: float
    answer: str
    answer_type: AnswerType
    label: str


class TemplatePageIn(BaseModel):
    page_index: int = Field(ge=0)
    image_id: int
    boxes: list[AnswerBoxIn] = Field(default_factory=list)

    @field_validator("boxes")
    @classmethod
    def _unique_question_numbers(cls, boxes: list[AnswerBoxIn]) -> list[AnswerBoxIn]:
        numbers = [b.question_no for b in boxes]
        if len(numbers) != len(set(numbers)):
            raise ValueError("同一頁的題號不可重複")
        return boxes


class TemplatePageOut(ORMModel):
    page_index: int
    image_id: int
    image_width: int
    image_height: int
    boxes: list[AnswerBoxOut]


class TemplateCreate(BaseModel):
    exam_name: str = Field(min_length=1, max_length=255)
    grade: str | None = Field(default=None, max_length=20)
    subject: str | None = Field(default=None, max_length=20)
    pages: list[TemplatePageIn] = Field(min_length=1)

    @field_validator("pages")
    @classmethod
    def _unique_page_indexes(cls, pages: list[TemplatePageIn]) -> list[TemplatePageIn]:
        indexes = [p.page_index for p in pages]
        if len(indexes) != len(set(indexes)):
            raise ValueError("頁碼不可重複")
        return pages


class TemplateUpdate(BaseModel):
    exam_name: str | None = Field(default=None, min_length=1, max_length=255)
    grade: str | None = Field(default=None, max_length=20)
    subject: str | None = Field(default=None, max_length=20)
    pages: list[TemplatePageIn] | None = None


class TemplateSummary(BaseModel):
    id: int
    exam_name: str
    grade: str | None
    subject: str | None
    annotation_count: int
    page_count: int
    revision: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    master_url: str | None = None


class TemplateDetail(TemplateSummary):
    pages: list[TemplatePageOut]


class TemplateListResponse(BaseModel):
    templates: list[TemplateSummary]
    # Feed straight back as `updated_since` next time. Computed server-side so
    # a client never has to reason about clock skew between phone and server.
    sync_cursor: datetime | None = None


# ── 批改結果 ─────────────────────────────────────────────────────────────────


class GradedAnswerIn(BaseModel):
    question_no: int = Field(ge=1)
    expected: str = ""
    recognized: str | None = None
    verdict: Verdict
    confidence: float | None = Field(default=None, ge=0, le=1)
    margin: float | None = Field(default=None, ge=0, le=1)
    teacher_value: str | None = None
    cell_image_id: int | None = None


class GradedAnswerOut(ORMModel):
    question_no: int
    expected: str
    recognized: str | None
    verdict: Verdict
    confidence: float | None
    margin: float | None
    teacher_value: str | None
    corrected_at: datetime | None
    cell_image_id: int | None


class GradingSessionIn(BaseModel):
    template_id: int
    student_id: int | None = None
    image_id: int | None = None
    scanned_at: datetime
    app_version: str | None = Field(default=None, max_length=40)
    answers: list[GradedAnswerIn] = Field(default_factory=list)

    @field_validator("answers")
    @classmethod
    def _unique_question_numbers(cls, answers: list[GradedAnswerIn]) -> list[GradedAnswerIn]:
        numbers = [a.question_no for a in answers]
        if len(numbers) != len(set(numbers)):
            raise ValueError("題號不可重複")
        return answers


class GradingSessionOut(BaseModel):
    id: int
    client_uuid: uuid.UUID
    template_id: int
    template_name: str | None = None
    student_id: int | None
    teacher_id: int | None
    image_id: int | None
    scanned_at: datetime
    uploaded_at: datetime
    correct_count: int
    total_count: int
    app_version: str | None
    answers: list[GradedAnswerOut]


class GradingSessionSummary(BaseModel):
    id: int
    client_uuid: uuid.UUID
    template_id: int
    template_name: str | None = None
    student_id: int | None
    scanned_at: datetime
    correct_count: int
    total_count: int


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    class_name: str | None = Field(default=None, max_length=60)
    external_id: str | None = Field(default=None, max_length=60)


class StudentOut(ORMModel):
    id: int
    name: str
    class_name: str | None
    external_id: str | None
