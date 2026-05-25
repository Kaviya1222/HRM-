from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.constants import REFRESH_TOKEN_TYPE, RoleCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_value,
    verify_password,
)
from app.models.auth import User, UserSession
from app.services.permission_service import PermissionService
from app.services.tracker_service import TrackerService


class AuthService:
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> User:
        normalized_email = email.strip().lower()
        user = db.execute(select(User).options(joinedload(User.role)).where(User.email == normalized_email)).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
        return user

    @staticmethod
    def build_current_user_payload(db: Session, user: User) -> dict[str, object]:
        effective_access = PermissionService.get_effective_access(db, user)
        employee_id = user.employee_profile.id if user.employee_profile else None
        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "role": {
                "id": user.role.id,
                "code": user.role.code,
                "name": user.role.name,
                "hierarchy_rank": user.role.hierarchy_rank,
            },
            "employee_id": employee_id,
            "permissions": sorted(effective_access.permission_keys),
            "is_super_admin": effective_access.is_super_admin,
            "last_login_at": user.last_login_at,
        }

    @staticmethod
    def login(
        db: Session,
        *,
        email: str,
        password: str,
        device_name: str | None = None,
        device_type: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, object]:
        user = AuthService.authenticate_user(db, email, password)
        now = datetime.now(UTC)

        session = UserSession(
            user_id=user.id,
            access_jti="pending",
            refresh_jti="pending",
            refresh_token_hash="pending",
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
            last_activity_at=now,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        db.add(session)
        db.flush()

        access_token, access_jti = create_access_token(subject=str(user.id), session_id=str(session.id), role_code=user.role.code)
        refresh_token, refresh_jti = create_refresh_token(subject=str(user.id), session_id=str(session.id), role_code=user.role.code)

        session.access_jti = access_jti
        session.refresh_jti = refresh_jti
        session.refresh_token_hash = hash_value(refresh_token)
        user.last_login_at = now

        db.commit()
        db.refresh(user)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": AuthService.build_current_user_payload(db, user),
        }

    @staticmethod
    def refresh_session(
        db: Session,
        *,
        refresh_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, object]:
        try:
            payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc

        session = db.execute(
            select(UserSession)
            .options(joinedload(UserSession.user).joinedload(User.role), joinedload(UserSession.user).joinedload(User.employee_profile))
            .where(UserSession.id == payload.sid)
        ).scalar_one_or_none()

        if session is None or session.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is no longer active")
        if session.refresh_jti != payload.jti or session.refresh_token_hash != hash_value(refresh_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token mismatch")
        if session.expires_at <= datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired")
        if not session.user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

        access_token, access_jti = create_access_token(subject=str(session.user.id), session_id=str(session.id), role_code=session.user.role.code)
        new_refresh_token, refresh_jti = create_refresh_token(subject=str(session.user.id), session_id=str(session.id), role_code=session.user.role.code)

        session.access_jti = access_jti
        session.refresh_jti = refresh_jti
        session.refresh_token_hash = hash_value(new_refresh_token)
        session.ip_address = ip_address or session.ip_address
        session.user_agent = user_agent or session.user_agent
        session.last_activity_at = datetime.now(UTC)
        session.expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": AuthService.build_current_user_payload(db, session.user),
        }

    @staticmethod
    def logout(db: Session, *, session: UserSession) -> None:
        if session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            session.last_activity_at = datetime.now(UTC)
            db.commit()
        if session.user:
            TrackerService.sync_dashboard_logout(db, session.user)
