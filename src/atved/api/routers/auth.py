"""Authentication and token endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atved.api import deps
from atved.db.models import StaffUser
from atved.core.security import verify_password, create_jwt
from atved.schemas.auth import TokenResponse
from atved.config import settings

router = APIRouter(tags=["Auth"])


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(deps.get_db),
):
    """OAuth2 compatible token login, getting an access token for future requests."""
    result = await db.execute(select(StaffUser).where(StaffUser.username == form_data.username))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token = create_jwt(
        data={"sub": str(user.id), "role": user.role.value},
        secret=settings.api.jwt_secret,
        algorithm=settings.api.jwt_algorithm,
        expires_minutes=settings.api.jwt_expiration_minutes
    )
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "expires_in": settings.api.jwt_expiration_minutes * 60
    }
