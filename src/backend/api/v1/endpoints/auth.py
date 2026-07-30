"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_role
from models.user import User
from services.auth_service import AuthService, AuthenticationError, PermissionDenied

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class FirstAccessRequest(BaseModel):
    username: str
    password: str
    password_confirm: str


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    password_set: bool = True

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    user: UserResponse


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class LogoutResponse(BaseModel):
    ok: bool = True


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        result = service.authenticate(request.username, request.password)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type="bearer",
        expires_in=result.expires_in,
        user=UserResponse(
            id=str(result.user.id),
            username=result.user.username,
            email=result.user.email,
            role=result.user.role,
            is_active=result.user.is_active,
            password_set=result.user.password_set,
        ),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        pair = service.refresh(request.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return RefreshResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type="bearer",
        expires_in=pair.expires_in,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: LogoutRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    service.logout(request.refresh_token)
    return LogoutResponse(ok=True)


@router.post("/first-access", response_model=UserResponse)
def first_access(
    request: FirstAccessRequest,
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    try:
        user = service.first_access(
            request.username, request.password, request.password_confirm
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        password_set=user.password_set,
    )


@router.post("/register", response_model=UserResponse)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin")),
):
    service = AuthService(db)
    try:
        user = service.register(request.model_dump(), current_user)
    except PermissionDenied as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        password_set=user.password_set,
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
        password_set=current_user.password_set,
    )
