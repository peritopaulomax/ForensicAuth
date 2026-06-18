"""User management endpoints (admin only)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_role
from models.user import User
from services.auth_service import PermissionDenied
from services.user_service import UserService

router = APIRouter()


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    password_set: bool

    class Config:
        from_attributes = True


class ProvisionUserRequest(BaseModel):
    username: str
    email: EmailStr
    role: str


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        password_set=user.password_set,
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    service = UserService(db)
    return [_to_response(u) for u in service.list_users()]


@router.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
def provision_user(
    request: ProvisionUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    service = UserService(db)
    try:
        user = service.provision_user(request.model_dump(), current_user)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return _to_response(user)


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    request: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    service = UserService(db)
    data = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        user = service.update_user(user_id, data, current_user)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return _to_response(user)


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    service = UserService(db)
    try:
        user = service.reset_password(user_id, current_user)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return _to_response(user)
