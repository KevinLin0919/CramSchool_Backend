from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Student, Teacher
from ..schemas import StudentIn, StudentOut
from ..security import current_teacher

router = APIRouter(prefix="/api/v1/students", tags=["students"])


@router.get("", response_model=list[StudentOut], summary="列出學生")
def list_students(
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
    search: str | None = None,
    class_name: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[Student]:
    query = select(Student)
    if search:
        query = query.where(Student.name.ilike(f"%{search}%"))
    if class_name:
        query = query.where(Student.class_name == class_name)
    return list(db.execute(query.order_by(Student.name).limit(limit)).scalars().all())


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(
    payload: StudentIn,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Student:
    student = Student(**payload.model_dump())
    db.add(student)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="學號重複") from exc
    db.refresh(student)
    return student


@router.patch("/{student_id}", response_model=StudentOut)
def update_student(
    student_id: int,
    payload: StudentIn,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Student:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="找不到學生")
    for key, value in payload.model_dump().items():
        setattr(student, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="學號重複") from exc
    db.refresh(student)
    return student


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(
    student_id: int,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Response:
    student = db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="找不到學生")
    db.delete(student)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
