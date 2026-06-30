from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from fastapi import Request
from fastapi.responses import RedirectResponse
from passlib.context import CryptContext

from app.db import Database

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
)

T = TypeVar("T")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    return pwd_context.verify(password, hashed_password)


def has_admin_password(db: Database) -> bool:
    return bool(db.get_setting("admin_password_hash"))


def login_required(
    handler: Callable[..., T],
) -> Callable[..., T | RedirectResponse]:
    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> T | RedirectResponse:
        request: Request = kwargs["request"]
        db: Database = request.app.state.db
        if not has_admin_password(db):
            return RedirectResponse(url="/setup", status_code=303)
        if not request.session.get("authenticated"):
            return RedirectResponse(url="/login", status_code=303)
        return await handler(*args, **kwargs)

    return wrapper
