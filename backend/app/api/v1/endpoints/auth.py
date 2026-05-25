from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_auth_context, get_db
from app.schemas.auth import AuthResponse, CurrentUserSchema, LoginRequest, LogoutRequest, RefreshTokenRequest
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    return AuthService.login(
        db,
        email=payload.email,
        password=payload.password,
        device_name=payload.device_name,
        device_type=payload.device_type,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh_tokens(payload: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    return AuthService.refresh_session(
        db,
        refresh_token=payload.refresh_token,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    payload: LogoutRequest,
    auth: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> MessageResponse:
    AuthService.logout(db, session=auth.session)
    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=CurrentUserSchema)
def current_user(auth: AuthContext = Depends(get_current_auth_context), db: Session = Depends(get_db)) -> dict[str, object]:
    return AuthService.build_current_user_payload(db, auth.user)
