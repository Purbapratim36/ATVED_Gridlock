"""
FastAPI dependencies.

Database sessions, authentication, and role-based access control.
"""

from __future__ import annotations

from typing import AsyncGenerator
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atved.db.session import async_session_maker
from atved.db.models import StaffUser, StaffRole
from atved.core.security import decode_jwt
from atved.config import settings
from atved.core.audit import AuditWriter

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/token")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: Yields an async database session."""
    async with async_session_maker() as session:
        yield session


def get_audit_writer() -> AuditWriter:
    """Dependency: Returns the audit writer instance."""
    return AuditWriter()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> StaffUser:
    """Dependency: Validates JWT token and retrieves the current staff user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_jwt(
            token, 
            secret=settings.api.jwt_secret,
            algorithm=settings.api.jwt_algorithm
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
        
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        raise credentials_exception

    result = await db.execute(select(StaffUser).where(StaffUser.id == user_uuid))
    user = result.scalar_one_or_none()
    
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user


def require_role(allowed_roles: list[StaffRole]):
    """Dependency factory for RBAC."""
    async def role_checker(current_user: StaffUser = Depends(get_current_user)) -> StaffUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted for your role"
            )
        return current_user
    return role_checker
