from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_db, require_any_permissions, require_permissions, require_tracker_token
from app.schemas.tracker import (
    RegisterDeviceRequest,
    TrackerHeartbeatRequest,
    TrackerIdleEndRequest,
    TrackerIdleStartRequest,
    TrackerStatusUpdateRequest,
    TrackerSessionEndRequest,
    TrackerSessionStartRequest,
    WebTrackerCheckInRequest,
    WebTrackerHeartbeatRequest,
    WebTrackerLogoutRequest,
)
from app.services.tracker_service import TrackerService

router = APIRouter()


@router.get("/monitor")
def monitor_tracker(
    auth: AuthContext = Depends(require_any_permissions("tracker.monitor", "tracker.view.device")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.monitor(db, auth)


@router.get("/live-status")
def live_tracker_status(
    auth: AuthContext = Depends(require_any_permissions("tracker.monitor", "tracker.view.device")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.monitor(db, auth)


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/checkin")
def web_tracker_checkin(
    payload: WebTrackerCheckInRequest,
    request: Request,
    auth: AuthContext = Depends(require_permissions("attendance.check_in")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.web_check_in(
        db,
        auth,
        check_in_at=payload.check_in_at,
        device_info=payload.device_info,
        ip_address=_client_ip(request),
    )


@router.post("/heartbeat")
def web_tracker_heartbeat(
    payload: WebTrackerHeartbeatRequest,
    request: Request,
    auth: AuthContext = Depends(require_permissions("attendance.check_in")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.web_heartbeat(
        db,
        auth,
        heartbeat_at=payload.heartbeat_at,
        is_idle=payload.is_idle,
        device_info=payload.device_info,
        ip_address=_client_ip(request),
    )


@router.post("/logout")
def web_tracker_logout(
    payload: WebTrackerLogoutRequest,
    auth: AuthContext = Depends(require_permissions("attendance.check_in")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.web_logout(
        db,
        auth,
        logout_time=payload.logout_time,
        reason=payload.reason,
    )


@router.post("/register-device")
def register_device(
    payload: RegisterDeviceRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.register_device(db, payload.model_dump())


@router.post("/start-session")
def start_tracker_session(
    payload: TrackerSessionStartRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.start_session(db, payload.model_dump())


@router.post("/end-session")
def end_tracker_session(
    payload: TrackerSessionEndRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.end_session(db, payload.model_dump())


@router.post("/idle-start")
def start_idle(
    payload: TrackerIdleStartRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.idle_start(db, payload.model_dump())


@router.post("/idle-end")
def end_idle(
    payload: TrackerIdleEndRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.idle_end(db, payload.model_dump())


@router.post("/client-heartbeat")
def tracker_client_heartbeat(
    payload: TrackerHeartbeatRequest,
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.heartbeat(db, payload.model_dump())


@router.post("/status")
def update_tracker_status(
    payload: TrackerStatusUpdateRequest,
    auth: AuthContext = Depends(require_permissions("attendance.check_in")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.update_dashboard_status(
        db,
        auth,
        status_value=payload.status,
        last_active_time=payload.last_active_time,
    )


@router.post("/offline-sync/{event_type}")
def offline_sync_tracker_event(
    event_type: str,
    payload: dict[str, object],
    _: str = Depends(require_tracker_token),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return TrackerService.offline_sync(db, event_type, payload)
