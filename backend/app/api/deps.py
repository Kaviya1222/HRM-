from __future__ import annotations

from dataclasses import dataclass
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import ACCESS_TOKEN_TYPE
from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db_session
from app.models.auth import User, UserSession
from app.services.permission_service import EffectiveAccess, PermissionService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
tracker_bearer = HTTPBearer(auto_error=False)

@dataclass(slots=True)
class AuthContext:
    user: User
    session: UserSession
    access: EffectiveAccess


def get_db(db: Session = Depends(get_db_session)) -> Session:
    return db


def get_current_auth_context(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> AuthContext:
    try:
        payload = decode_token(token, expected_type=ACCESS_TOKEN_TYPE)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc

    session = db.execute(
        select(UserSession)
        .options(joinedload(UserSession.user).joinedload(User.role), joinedload(UserSession.user).joinedload(User.employee_profile))
        .where(UserSession.id == payload.sid)
    ).scalar_one_or_none()

    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is not active")
    if session.access_jti != payload.jti:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token has been rotated")
    if not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    access = PermissionService.get_effective_access(db, session.user)
    return AuthContext(user=session.user, session=session, access=access)


def require_super_admin(auth: AuthContext = Depends(get_current_auth_context)) -> AuthContext:
    if not auth.access.is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin can access this section")
    return auth


def require_permissions(*permission_keys: str):
    def dependency(auth: AuthContext = Depends(get_current_auth_context)) -> AuthContext:
        if not PermissionService.has_permissions(auth.access, permission_keys):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        if not all(PermissionService.has_module_access(auth.access, permission) for permission in permission_keys):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return auth

    return dependency


def require_any_permissions(*permission_keys: str):
    def dependency(auth: AuthContext = Depends(get_current_auth_context)) -> AuthContext:
        if auth.access.is_super_admin or "*" in auth.access.permission_keys:
            return auth
        has_any_allowed_permission = PermissionService.has_any_permission_with_module(auth.access, permission_keys)
        if not has_any_allowed_permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return auth

    return dependency


def require_tracker_token(credentials: HTTPAuthorizationCredentials | None = Depends(tracker_bearer)) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tracker token is required")
    if not secrets.compare_digest(credentials.credentials, settings.tracker_shared_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid tracker token")
    return credentials.credentials
