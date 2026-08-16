"""Admin CLI — `cramctl`, or `python -m app.cli`.

Everything an operator needs that has no business being an HTTP endpoint:
creating the first admin, enrolling teachers, and killing a token when a device
goes missing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import typer
from sqlalchemy import select

from .db import SessionLocal
from .models import ApiToken, InviteCode, Teacher
from .security import generate_token, hash_token

app = typer.Typer(help="補習班批改系統管理工具", no_args_is_help=True)
teachers_app = typer.Typer(help="教師帳號")
tokens_app = typer.Typer(help="裝置 token")
app.add_typer(teachers_app, name="teachers")
app.add_typer(tokens_app, name="tokens")


@teachers_app.command("add")
def add_teacher(
    name: str = typer.Argument(..., help="姓名"),
    email: str | None = typer.Option(None, help="電子郵件"),
    admin: bool = typer.Option(False, "--admin", help="建立為管理員"),
) -> None:
    with SessionLocal() as db:
        teacher = Teacher(name=name, email=email, role="admin" if admin else "teacher")
        db.add(teacher)
        db.commit()
        db.refresh(teacher)
        typer.echo(f"已建立 #{teacher.id} {teacher.name}（{teacher.role}）")


@teachers_app.command("list")
def list_teachers() -> None:
    with SessionLocal() as db:
        rows = db.execute(select(Teacher).order_by(Teacher.id)).scalars().all()
        if not rows:
            typer.echo("（尚無教師）")
            return
        for t in rows:
            state = "停用" if t.disabled_at else "啟用"
            active = sum(1 for tk in t.tokens if tk.revoked_at is None)
            typer.echo(f"#{t.id:<4} {t.name:<12} {t.role:<8} {state}  裝置 {active}")


@teachers_app.command("disable")
def disable_teacher(teacher_id: int) -> None:
    """Disabling revokes every device at once — one action, not a hunt."""
    with SessionLocal() as db:
        teacher = db.get(Teacher, teacher_id)
        if teacher is None:
            raise typer.BadParameter("找不到教師")
        now = datetime.now(UTC)
        teacher.disabled_at = now
        for token in teacher.tokens:
            if token.revoked_at is None:
                token.revoked_at = now
        db.commit()
        typer.echo(f"已停用 {teacher.name} 並撤銷所有裝置")


@teachers_app.command("invite")
def invite(
    teacher_id: int,
    days: int = typer.Option(7, help="有效天數"),
) -> None:
    """Prints a single-use enrolment code. Only shown once."""
    with SessionLocal() as db:
        teacher = db.get(Teacher, teacher_id)
        if teacher is None:
            raise typer.BadParameter("找不到教師")
        code = generate_token()
        db.add(
            InviteCode(
                code_hash=hash_token(code),
                teacher_id=teacher.id,
                expires_at=datetime.now(UTC) + timedelta(days=days),
            )
        )
        db.commit()

    typer.echo(f"\n給 {teacher.name} 的邀請碼（{days} 天內有效，只顯示這一次）：\n")
    typer.echo(f"    {code}\n")


@tokens_app.command("list")
def list_tokens() -> None:
    with SessionLocal() as db:
        rows = db.execute(select(ApiToken).order_by(ApiToken.id)).scalars().all()
        if not rows:
            typer.echo("（尚無裝置）")
            return
        for tk in rows:
            state = "已撤銷" if tk.revoked_at else "使用中"
            last = tk.last_used_at.strftime("%Y-%m-%d %H:%M") if tk.last_used_at else "從未"
            typer.echo(
                f"#{tk.id:<4} {tk.teacher.name:<12} {tk.device_name or '(未命名)':<20} "
                f"{state:<8} 最後使用 {last}"
            )


@tokens_app.command("revoke")
def revoke_token(token_id: int) -> None:
    with SessionLocal() as db:
        token = db.get(ApiToken, token_id)
        if token is None:
            raise typer.BadParameter("找不到 token")
        token.revoked_at = datetime.now(UTC)
        db.commit()
        typer.echo(f"已撤銷 #{token_id}（{token.teacher.name}）")


if __name__ == "__main__":
    app()
