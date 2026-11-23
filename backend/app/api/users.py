"""User management and audit log (v2.3.0). Admin only."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserOut, require
from app.db.database import get_db
from app.models.audit_log import AuditLog
from app.models.user import ROLES, User
from app.services import audit
from app.services.security import hash_password

router = APIRouter()
audit_router = APIRouter()

MIN_PASSWORD = 8


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=MIN_PASSWORD)
    display_name: Optional[str] = None
    role: str = "user"
    extensions: list[str] = []


class UserPatch(BaseModel):
    display_name: Optional[str] = None
    role: Optional[str] = None
    extensions: Optional[list[str]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=MIN_PASSWORD)


class UserAdminOut(UserOut):
    is_active: bool
    last_login: Optional[str] = None

    @classmethod
    def of(cls, u: User) -> "UserAdminOut":
        return cls(id=u.id, username=u.username, display_name=u.display_name, role=u.role,
                   extensions=u.extension_list, is_active=u.is_active,
                   last_login=u.last_login.isoformat() if u.last_login else None)


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"Role must be one of: {', '.join(ROLES)}")


def _join(extensions: list[str]) -> str:
    return ",".join(dict.fromkeys(e.strip() for e in extensions if e.strip()))


async def _active_admins(db: AsyncSession) -> int:
    return (await db.execute(
        select(func.count(User.id)).where(User.role == "admin", User.is_active.is_(True))
    )).scalar() or 0


async def _get(db: AsyncSession, user_id: int) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=list[UserAdminOut])
async def list_users(db: AsyncSession = Depends(get_db), _: User = Depends(require("users.manage"))):
    rows = (await db.execute(select(User).order_by(User.username))).scalars().all()
    return [UserAdminOut.of(u) for u in rows]


@router.post("", response_model=UserAdminOut, status_code=201)
async def create_user(body: UserCreate, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(require("users.manage"))):
    _check_role(body.role)
    username = body.username.strip()
    if (await db.execute(select(User).where(User.username == username))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=username, display_name=body.display_name, role=body.role,
                extensions=_join(body.extensions), password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()
    await audit.record(db, admin, "user.create", request=request, detail=f"{username} ({body.role})")
    return UserAdminOut.of(user)


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(user_id: int, body: UserPatch, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(require("users.manage"))):
    user = await _get(db, user_id)
    losing_admin = (user.role == "admin" and user.is_active) and (
        (body.role is not None and body.role != "admin") or body.is_active is False)
    if losing_admin and await _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove or disable the last active admin")
    if body.is_active is False and user.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")

    changes = []
    if body.role is not None:
        _check_role(body.role)
        user.role = body.role
        changes.append(f"role={body.role}")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.extensions is not None:
        user.extensions = _join(body.extensions)
        changes.append("extensions")
    if body.is_active is not None:
        user.is_active = body.is_active
        changes.append(f"active={body.is_active}")
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        changes.append("password reset")
    await db.flush()
    await audit.record(db, admin, "user.update", request=request,
                       detail=f"{user.username}: {', '.join(changes) or 'no change'}")
    return UserAdminOut.of(user)


@router.delete("/{user_id}")
async def delete_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(require("users.manage"))):
    user = await _get(db, user_id)
    if user.id == admin.id:
        raise HTTPException(status_code=409, detail="You cannot delete your own account")
    if user.role == "admin" and user.is_active and await _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="Cannot delete the last active admin")
    name = user.username
    await db.delete(user)
    await db.flush()
    await audit.record(db, admin, "user.delete", request=request, detail=name)
    return {"deleted": user_id}


@audit_router.get("")
async def list_audit(
    action: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    call_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require("audit.view")),
):
    q = select(AuditLog).order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
    if action:
        q = q.where(AuditLog.action == action)
    if username:
        q = q.where(AuditLog.username == username)
    if call_id is not None:
        q = q.where(AuditLog.call_id == call_id)
    rows = (await db.execute(q.offset(skip).limit(limit))).scalars().all()
    return [{"id": r.id, "timestamp": r.timestamp.isoformat() if r.timestamp else None,
             "username": r.username, "action": r.action, "call_id": r.call_id,
             "ip": r.ip, "detail": r.detail} for r in rows]
