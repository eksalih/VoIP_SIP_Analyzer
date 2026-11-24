"""Login and current-user endpoints (v2.3.0). Roles/permissions are enforced in a later step."""
import logging
import os
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import get_db
from app.models.user import User
from app.services import audit
from app.services.permissions import ROLE_PERMISSIONS, has_permission
from app.services.security import create_token, decode_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    display_name: Optional[str] = None
    role: str
    extensions: list[str] = []
    permissions: list[str] = []   # "*" means everything

    @classmethod
    def of(cls, u: User) -> "UserOut":
        return cls(id=u.id, username=u.username, display_name=u.display_name,
                   role=u.role, extensions=u.extension_list,
                   permissions=sorted(ROLE_PERMISSIONS.get(u.role, set())))


async def get_current_user(
    authorization: Optional[str] = Header(None), db: AsyncSession = Depends(get_db)
) -> User:
    token = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None
    user_id = decode_token(token) if token else None
    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require(*permissions: str):
    """Dependency: the current user must hold at least one of the given permissions."""
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not any(has_permission(user, p) for p in permissions):
            raise HTTPException(status_code=403, detail="You do not have permission to do this")
        return user
    return dependency


@router.post("/login")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.username == body.username.strip()))).scalar_one_or_none()
    # Same error for unknown user and wrong password
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        await audit.record(db, user, "login_failed", request=request, username=body.username.strip()[:64])
        raise HTTPException(status_code=401, detail="Invalid username or password")
    user.last_login = datetime.utcnow()
    await audit.record(db, user, "login", request=request)
    return {"token": create_token(user.id), "user": UserOut.of(user)}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/change-password")
async def change_password(body: PasswordChange, request: Request, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await audit.record(db, user, "password.change", request=request)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut.of(user)


async def bootstrap_admin(session_factory: async_sessionmaker) -> Optional[str]:
    """
    On a fresh install (no users) create the first admin from ADMIN_USERNAME /
    ADMIN_PASSWORD. Without ADMIN_PASSWORD a random one is generated and logged once.
    Returns the generated password if one was created, else None.
    """
    async with session_factory() as db:
        if (await db.execute(select(func.count(User.id)))).scalar():
            return None
        username = os.getenv("ADMIN_USERNAME", "admin")
        password = os.getenv("ADMIN_PASSWORD")
        generated = None
        if not password:
            password = generated = secrets.token_urlsafe(12)
        db.add(User(username=username, display_name="Administrator",
                    password_hash=hash_password(password), role="admin"))
        await db.commit()
    if generated:
        logger.warning(f"Created first admin '{username}' with generated password: {generated} "
                       "(set ADMIN_PASSWORD to choose your own; change it after first login)")
    else:
        logger.info(f"Created first admin '{username}'")
    return generated
