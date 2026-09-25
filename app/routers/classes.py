"""A teacher's classes and their rosters.

Names only. The roster exists so a paper can be matched to a child by picking
from a short list, which is reliable, instead of by reading handwriting, which
is not.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Enrollment, SchoolClass, Student, Teacher
from ..schemas import ClassIn, ClassOut, RosterStudentIn, StudentOut
from ..scope import owned_class
from ..security import current_teacher

router = APIRouter(prefix="/api/v1/classes", tags=["classes"])


def _out(school_class: SchoolClass) -> ClassOut:
    students = sorted((e.student for e in school_class.enrollments), key=lambda s: s.id)
    return ClassOut(id=school_class.id, name=school_class.name,
                    is_simulated=school_class.is_simulated,
                    students=[StudentOut.model_validate(s) for s in students])


def _load(db: Session, class_id: int) -> SchoolClass:
    return db.execute(
        select(SchoolClass)
        .options(selectinload(SchoolClass.enrollments).selectinload(Enrollment.student))
        .where(SchoolClass.id == class_id)
    ).scalar_one()


@router.get("", response_model=list[ClassOut], summary="我的班級與名冊")
def list_classes(db: Session = Depends(get_db),
                 teacher: Teacher = Depends(current_teacher)) -> list[ClassOut]:
    rows = db.execute(
        select(SchoolClass)
        .options(selectinload(SchoolClass.enrollments).selectinload(Enrollment.student))
        .where(SchoolClass.teacher_id == teacher.id)
        .order_by(SchoolClass.is_simulated, SchoolClass.name)
    ).scalars().all()
    return [_out(c) for c in rows]


@router.post("", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
def create_class(payload: ClassIn, db: Session = Depends(get_db),
                 teacher: Teacher = Depends(current_teacher)) -> ClassOut:
    school_class = SchoolClass(teacher_id=teacher.id, name=payload.name.strip())
    db.add(school_class)
    db.commit()
    return _out(_load(db, school_class.id))


@router.patch("/{class_id}", response_model=ClassOut)
def rename_class(class_id: int, payload: ClassIn, db: Session = Depends(get_db),
                 teacher: Teacher = Depends(current_teacher)) -> ClassOut:
    owned_class(db, teacher, class_id).name = payload.name.strip()
    db.commit()
    return _out(_load(db, class_id))


@router.post("/{class_id}/students", response_model=ClassOut,
             status_code=status.HTTP_201_CREATED, summary="加一位學生到名冊")
def add_student(class_id: int, payload: RosterStudentIn, db: Session = Depends(get_db),
                teacher: Teacher = Depends(current_teacher)) -> ClassOut:
    owned_class(db, teacher, class_id)
    student = Student(name=payload.name.strip())
    db.add(student)
    db.flush()
    db.add(Enrollment(class_id=class_id, student_id=student.id))
    db.commit()
    return _out(_load(db, class_id))


@router.patch("/{class_id}/students/{student_id}", response_model=ClassOut)
def rename_student(class_id: int, student_id: int, payload: RosterStudentIn,
                   db: Session = Depends(get_db),
                   teacher: Teacher = Depends(current_teacher)) -> ClassOut:
    school_class = owned_class(db, teacher, class_id)
    enrolment = next((e for e in school_class.enrollments if e.student_id == student_id), None)
    if enrolment is None:
        raise HTTPException(status_code=404, detail="這位學生不在名冊上")
    enrolment.student.name = payload.name.strip()
    db.commit()
    return _out(_load(db, class_id))


@router.delete("/{class_id}/students/{student_id}", status_code=204,
               summary="從名冊移除（不刪除已批改紀錄）")
def remove_student(class_id: int, student_id: int, db: Session = Depends(get_db),
                   teacher: Teacher = Depends(current_teacher)) -> Response:
    school_class = owned_class(db, teacher, class_id)
    enrolment = next((e for e in school_class.enrollments if e.student_id == student_id), None)
    if enrolment is None:
        raise HTTPException(status_code=404, detail="這位學生不在名冊上")
    # The enrolment goes; the student row and every paper matched to them stay.
    db.delete(enrolment)
    db.commit()
    return Response(status_code=204)
