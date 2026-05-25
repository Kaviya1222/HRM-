from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.auth import User
from app.models.employee import Employee
from app.models.enums import DeviceStatus, TrackerSessionStatus
from app.models.tracker import Device, TrackerHeartbeat, TrackerIdleLog, TrackerSession
from app.services.user_scope_service import UserScopeService


class TrackerService:
    DASHBOARD_DEVICE_PREFIX = "dashboard-session-"
    ONLINE_STALE_SECONDS = 60

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    @staticmethod
    def _dashboard_device_uuid(principal_id: str) -> str:
        return f"{TrackerService.DASHBOARD_DEVICE_PREFIX}{principal_id}"

    @staticmethod
    def _find_device(db: Session, device_uuid: str) -> Device | None:
        return db.execute(select(Device).where(Device.device_uuid == device_uuid)).scalar_one_or_none()

    @staticmethod
    def _find_active_session(db: Session, device_id: str) -> TrackerSession | None:
        return db.execute(
            select(TrackerSession)
            .where(
                TrackerSession.device_id == device_id,
                TrackerSession.status == TrackerSessionStatus.ACTIVE.value,
            )
            .order_by(TrackerSession.started_at.desc(), TrackerSession.created_at.desc())
        ).scalars().first()

    @staticmethod
    def _find_active_dashboard_session(db: Session, principal_id: str) -> TrackerSession | None:
        dashboard_uuid = TrackerService._dashboard_device_uuid(principal_id)
        return db.execute(
            select(TrackerSession)
            .join(Device, TrackerSession.device_id == Device.id)
            .where(
                TrackerSession.employee_id == employee_id,
                TrackerSession.status == TrackerSessionStatus.ACTIVE.value,
                Device.device_uuid == dashboard_uuid,
            )
            .order_by(TrackerSession.started_at.desc())
        ).scalars().first()

    @staticmethod
    def _find_active_dashboard_sessions(db: Session, *, user: User, employee: Employee | None) -> list[TrackerSession]:
        principal_id = str(employee.id if employee else user.id)
        dashboard_uuid = TrackerService._dashboard_device_uuid(principal_id)
        conditions = [
            Device.device_uuid == dashboard_uuid,
            TrackerSession.user_id == user.id,
        ]
        if employee is not None:
            conditions.append(TrackerSession.employee_id == employee.id)

        return list(
            db.execute(
                select(TrackerSession)
                .join(Device, TrackerSession.device_id == Device.id)
                .where(
                    TrackerSession.status == TrackerSessionStatus.ACTIVE.value,
                    or_(*conditions),
                )
                .order_by(TrackerSession.started_at.desc(), TrackerSession.created_at.desc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _get_or_create_dashboard_device(db: Session, *, user: User, employee: Employee | None) -> Device:
        principal_id = str(employee.id if employee else user.id)
        device_uuid = TrackerService._dashboard_device_uuid(principal_id)
        device = TrackerService._find_device(db, device_uuid)
        if device is None:
            device = Device(
                employee_id=employee.id if employee else None,
                user_id=user.id,
                device_uuid=device_uuid,
                device_name="Dashboard Session",
                os_version="Web",
                status=DeviceStatus.ACTIVE.value,
                last_seen_at=TrackerService._utcnow(),
            )
            db.add(device)
            db.flush()
        else:
            device.employee_id = employee.id if employee else None
            device.user_id = user.id
            device.device_name = "Dashboard Session"
            device.os_version = "Web"
            device.status = DeviceStatus.ACTIVE.value
        return device

    @staticmethod
    def _apply_session_heartbeat(session: TrackerSession, device: Device, heartbeat_at: datetime, *, is_idle: bool = False, device_info: dict[str, object] | None = None) -> None:
        session.is_online = True
        session.status = TrackerSessionStatus.ACTIVE.value
        session.last_active_at = heartbeat_at
        session.last_heartbeat = heartbeat_at
        session.device_info = device_info or session.device_info
        session.logout_time = None
        session.ended_at = None
        device.last_seen_at = heartbeat_at
        if device_info:
            device.device_name = str(device_info.get("device_name") or device_info.get("browser") or "Dashboard Session")
            device.os_version = str(device_info.get("platform") or device_info.get("user_agent") or "Web")[:120]

    @staticmethod
    def _mark_stale_sessions_offline(db: Session, *, now: datetime | None = None) -> int:
        now = now or TrackerService._utcnow()
        stale_before = now - timedelta(seconds=TrackerService.ONLINE_STALE_SECONDS)
        stale_sessions = db.execute(
            select(TrackerSession).where(
                TrackerSession.status == TrackerSessionStatus.ACTIVE.value,
                TrackerSession.is_online.is_(True),
                TrackerSession.last_active_at.is_not(None),
                TrackerSession.last_active_at < stale_before,
            )
        ).scalars().all()
        for session in stale_sessions:
            session.is_online = False
        if stale_sessions:
            db.commit()
        return len(stale_sessions)

    @staticmethod
    def _resolve_last_active(session: TrackerSession, device: Device | None, heartbeat_at: datetime | None) -> datetime:
        return TrackerService._normalize_datetime(
            session.last_active_at
            or session.last_heartbeat
            or heartbeat_at
            or device.last_seen_at
            or session.logout_time
            or session.login_time
            or session.started_at
        )

    @staticmethod
    def _current_status(session: TrackerSession, *, last_active_at: datetime, now: datetime) -> str:
        if session.status == TrackerSessionStatus.CLOSED.value or session.logout_time is not None:
            return "offline"
        if not session.is_online:
            return "offline"
        if now - last_active_at > timedelta(seconds=TrackerService.ONLINE_STALE_SECONDS):
            return "offline"
        return "online"

    @staticmethod
    def _serialize_monitor_row(
        session: TrackerSession,
        employee: Employee | None,
        user: User | None,
        device: Device | None,
        *,
        last_active_at: datetime,
        current_status: str,
    ) -> dict[str, object]:
        employee_name = (
            employee.user.full_name
            if employee and employee.user and employee.user.full_name
            else employee.employee_code
            if employee
            else user.full_name
            if user and user.full_name
            else user.email
            if user
            else "Unknown User"
        )
        check_in_time = session.login_time or session.started_at
        return {
            "tracker_session_id": session.id,
            "employee_id": employee.id if employee else None,
            "user_id": user.id if user else session.user_id,
            "employee_name": employee_name,
            "employee_code": employee.employee_code if employee else (user.role.name if user and user.role else "User"),
            "login_time": check_in_time,
            "logout_time": session.logout_time,
            "last_heartbeat": last_active_at,
            "idle_minutes": session.total_idle_minutes,
            "active_status": current_status,
            "device_name": device.device_name if device else "Dashboard Session",
            "system": device.os_version if device else "Web",
            "device_info": session.device_info,
            "session_token": session.session_token,
            "session_status": session.status,
        }

    @staticmethod
    def register_device(db: Session, payload: dict[str, object]) -> dict[str, object]:
        email = str(payload["employee_email"]).strip().lower()
        user = db.execute(select(User).options(joinedload(User.employee_profile)).where(User.email == email)).scalar_one_or_none()
        if user is None or user.employee_profile is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee linked to the tracker email was not found")

        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            device = Device(
                employee_id=user.employee_profile.id,
                user_id=user.id,
                device_uuid=str(payload["device_uuid"]),
                device_name=str(payload["device_name"]),
                os_version=payload.get("os_version"),
                status=DeviceStatus.ACTIVE.value,
                last_seen_at=TrackerService._utcnow(),
            )
            db.add(device)
        else:
            device.employee_id = user.employee_profile.id
            device.user_id = user.id
            device.device_name = str(payload["device_name"])
            device.os_version = payload.get("os_version")
            device.last_seen_at = TrackerService._utcnow()
            device.status = DeviceStatus.ACTIVE.value

        db.commit()
        db.refresh(device)
        return {
            "device_id": device.id,
            "device_uuid": device.device_uuid,
            "employee_id": device.employee_id,
        }

    @staticmethod
    def start_session(db: Session, payload: dict[str, object]) -> dict[str, object]:
        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker device is not registered")

        active_session = TrackerService._find_active_session(db, str(device.id))
        if active_session is not None:
            return {"tracker_session_id": active_session.id, "message": "Active session already exists"}

        started_at = TrackerService._normalize_datetime(payload["session_start_at"])
        session = TrackerSession(
            device_id=device.id,
            employee_id=device.employee_id,
            user_id=device.user_id,
            started_at=started_at,
            login_time=started_at,
            status=TrackerSessionStatus.ACTIVE.value,
            is_online=True,
            last_active_at=started_at,
        )
        device.last_seen_at = started_at
        db.add(session)
        db.commit()
        db.refresh(session)
        return {"tracker_session_id": session.id, "message": "Tracker session started"}

    @staticmethod
    def end_session(db: Session, payload: dict[str, object]) -> dict[str, object]:
        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker device is not registered")

        session = db.get(TrackerSession, payload.get("tracker_session_id")) if payload.get("tracker_session_id") else TrackerService._find_active_session(db, str(device.id))
        if session is None:
            return {"message": "No active tracker session found"}

        session_end_at = TrackerService._normalize_datetime(payload["session_end_at"])
        session.ended_at = session_end_at
        session.logout_time = session_end_at
        session.is_online = False
        session.status = TrackerSessionStatus.CLOSED.value
        session.last_active_at = session_end_at
        device.last_seen_at = session_end_at
        db.commit()
        return {"message": "Tracker session ended", "tracker_session_id": session.id}

    @staticmethod
    def idle_start(db: Session, payload: dict[str, object]) -> dict[str, object]:
        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker device is not registered")

        session = db.get(TrackerSession, payload.get("tracker_session_id")) if payload.get("tracker_session_id") else TrackerService._find_active_session(db, str(device.id))
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker session not found")

        existing = db.execute(
            select(TrackerIdleLog).where(TrackerIdleLog.tracker_session_id == session.id, TrackerIdleLog.idle_end_at.is_(None))
        ).scalar_one_or_none()
        if existing is not None:
            return {"message": "Idle log already open", "tracker_session_id": session.id}

        db.add(
            TrackerIdleLog(
                tracker_session_id=session.id,
                idle_start_at=TrackerService._normalize_datetime(payload["idle_start_at"]),
            )
        )
        db.commit()
        return {"message": "Idle state started", "tracker_session_id": session.id}

    @staticmethod
    def idle_end(db: Session, payload: dict[str, object]) -> dict[str, object]:
        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker device is not registered")

        session = db.get(TrackerSession, payload.get("tracker_session_id")) if payload.get("tracker_session_id") else TrackerService._find_active_session(db, str(device.id))
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker session not found")

        idle_log = db.execute(
            select(TrackerIdleLog)
            .where(
                TrackerIdleLog.tracker_session_id == session.id,
                TrackerIdleLog.idle_end_at.is_(None),
            )
            .order_by(desc(TrackerIdleLog.idle_start_at))
        ).scalar_one_or_none()
        if idle_log is None:
            return {"message": "No open idle interval found", "tracker_session_id": session.id}

        idle_end_at = TrackerService._normalize_datetime(payload["idle_end_at"])
        idle_minutes = max(int((idle_end_at - idle_log.idle_start_at).total_seconds() // 60), 0)
        idle_log.idle_end_at = idle_end_at
        idle_log.idle_minutes = idle_minutes
        session.total_idle_minutes += idle_minutes
        session.last_active_at = idle_end_at
        db.commit()
        return {"message": "Idle state ended", "tracker_session_id": session.id, "idle_minutes": idle_minutes}

    @staticmethod
    def heartbeat(db: Session, payload: dict[str, object]) -> dict[str, object]:
        device = TrackerService._find_device(db, str(payload["device_uuid"]))
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracker device is not registered")

        session = db.get(TrackerSession, payload.get("tracker_session_id")) if payload.get("tracker_session_id") else TrackerService._find_active_session(db, str(device.id))
        heartbeat_at = TrackerService._normalize_datetime(payload["heartbeat_at"])
        db.add(
            TrackerHeartbeat(
                device_id=device.id,
                employee_id=device.employee_id,
                user_id=device.user_id,
                tracker_session_id=session.id if session else None,
                heartbeat_at=heartbeat_at,
                is_idle=bool(payload.get("is_idle", False)),
                payload={"device_name": payload.get("device_name")},
            )
        )
        device.last_seen_at = heartbeat_at
        if payload.get("device_name"):
            device.device_name = str(payload["device_name"])
        if session is not None:
            TrackerService._apply_session_heartbeat(
                session,
                device,
                heartbeat_at,
                is_idle=bool(payload.get("is_idle", False)),
                device_info={"device_name": payload.get("device_name")} if payload.get("device_name") else None,
            )
        db.commit()
        return {"message": "Heartbeat received"}

    @staticmethod
    def web_check_in(
        db: Session,
        auth: AuthContext,
        *,
        check_in_at: datetime | None = None,
        device_info: dict[str, object] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)

        now = TrackerService._normalize_datetime(check_in_at) or TrackerService._utcnow()
        device = TrackerService._get_or_create_dashboard_device(db, user=auth.user, employee=employee)
        session = TrackerService._find_active_session(db, str(device.id))
        if session is None:
            session = TrackerSession(
                device_id=device.id,
                employee_id=employee.id if employee else None,
                user_id=auth.user.id,
                started_at=now,
                login_time=now,
                status=TrackerSessionStatus.ACTIVE.value,
                is_online=True,
                last_active_at=now,
                last_heartbeat=now,
                session_token=secrets.token_urlsafe(32),
                device_info=device_info,
                ip_address=ip_address,
            )
            db.add(session)
        else:
            session.login_time = session.login_time or now
            session.session_token = session.session_token or secrets.token_urlsafe(32)
            session.ip_address = ip_address or session.ip_address
            TrackerService._apply_session_heartbeat(session, device, now, device_info=device_info)
        device.last_seen_at = now
        db.commit()
        db.refresh(session)
        return {
            "message": "Tracker session online",
            "tracker_session_id": session.id,
            "session_token": session.session_token,
            "status": "online",
            "last_heartbeat": session.last_heartbeat,
        }

    @staticmethod
    def web_heartbeat(
        db: Session,
        auth: AuthContext,
        *,
        heartbeat_at: datetime | None = None,
        is_idle: bool = False,
        device_info: dict[str, object] | None = None,
        ip_address: str | None = None,
    ) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)

        now = TrackerService._normalize_datetime(heartbeat_at) or TrackerService._utcnow()
        device = TrackerService._get_or_create_dashboard_device(db, user=auth.user, employee=employee)
        session = TrackerService._find_active_session(db, str(device.id))
        if session is None:
            return TrackerService.web_check_in(db, auth, check_in_at=now, device_info=device_info, ip_address=ip_address)

        db.add(
            TrackerHeartbeat(
                device_id=device.id,
                employee_id=employee.id if employee else None,
                user_id=auth.user.id,
                tracker_session_id=session.id,
                heartbeat_at=now,
                is_idle=is_idle,
                payload=device_info,
            )
        )
        session.ip_address = ip_address or session.ip_address
        TrackerService._apply_session_heartbeat(session, device, now, is_idle=is_idle, device_info=device_info)
        db.commit()
        return {
            "message": "Heartbeat received",
            "tracker_session_id": session.id,
            "status": "online",
            "last_heartbeat": session.last_heartbeat,
        }

    @staticmethod
    def web_logout(
        db: Session,
        auth: AuthContext,
        *,
        logout_time: datetime | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)

        sessions = TrackerService._find_active_dashboard_sessions(db, user=auth.user, employee=employee)
        if not sessions:
            return {"message": "No active tracker session found", "status": "offline"}

        now = TrackerService._normalize_datetime(logout_time) or TrackerService._utcnow()
        for session in sessions:
            device = db.get(Device, session.device_id)
            session.is_online = False
            session.last_active_at = now
            session.last_heartbeat = now
            if reason in {"checkout", "logout"}:
                session.logout_time = now
                session.ended_at = now
                session.status = TrackerSessionStatus.CLOSED.value
            if device is not None:
                device.last_seen_at = now
        db.commit()
        return {"message": "Tracker session offline", "tracker_session_id": sessions[0].id, "status": "offline"}

    @staticmethod
    def sync_dashboard_check_in(db: Session, auth: AuthContext, check_in_at: datetime) -> dict[str, object] | None:
        employee = UserScopeService.current_employee(auth)

        check_in_at = TrackerService._normalize_datetime(check_in_at)
        device = TrackerService._get_or_create_dashboard_device(db, user=auth.user, employee=employee)
        session = TrackerService._find_active_session(db, str(device.id))
        if session is None:
            session = TrackerSession(
                device_id=device.id,
                employee_id=employee.id if employee else None,
                user_id=auth.user.id,
                started_at=check_in_at,
                login_time=check_in_at,
                status=TrackerSessionStatus.ACTIVE.value,
                is_online=True,
                last_active_at=check_in_at,
                last_heartbeat=check_in_at,
                session_token=secrets.token_urlsafe(32),
                device_info={"device_name": "Dashboard Session", "source": "check_in"},
            )
            db.add(session)
        else:
            session.is_online = True
            session.status = TrackerSessionStatus.ACTIVE.value
            session.login_time = session.login_time or check_in_at
            session.last_active_at = check_in_at
            session.last_heartbeat = check_in_at
            session.session_token = session.session_token or secrets.token_urlsafe(32)
            session.logout_time = None
            session.ended_at = None
        device.last_seen_at = check_in_at
        db.commit()
        return {"message": "Tracker session synced"}

    @staticmethod
    def sync_dashboard_check_out(db: Session, auth: AuthContext, check_out_at: datetime) -> dict[str, object] | None:
        employee = UserScopeService.current_employee(auth)

        check_out_at = TrackerService._normalize_datetime(check_out_at)
        sessions = TrackerService._find_active_dashboard_sessions(db, user=auth.user, employee=employee)
        if not sessions:
            return {"message": "No active tracker session found"}

        for session in sessions:
            device = db.get(Device, session.device_id)
            session.logout_time = check_out_at
            session.ended_at = check_out_at
            session.is_online = False
            session.status = TrackerSessionStatus.CLOSED.value
            session.last_active_at = check_out_at
            session.last_heartbeat = check_out_at
            if device is not None:
                device.last_seen_at = check_out_at
        db.commit()
        return {"message": "Tracker session closed"}

    @staticmethod
    def sync_dashboard_logout(db: Session, user: User) -> dict[str, object] | None:
        employee = user.employee_profile

        sessions = TrackerService._find_active_dashboard_sessions(db, user=user, employee=employee)
        if not sessions:
            return {"message": "No active tracker session found"}

        now = TrackerService._utcnow()
        for session in sessions:
            device = db.get(Device, session.device_id)
            session.logout_time = session.logout_time or now
            session.ended_at = session.ended_at or now
            session.is_online = False
            session.status = TrackerSessionStatus.CLOSED.value
            session.last_active_at = now
            session.last_heartbeat = now
            if device is not None:
                device.last_seen_at = now
        db.commit()
        return {"message": "Tracker session logged out"}

    @staticmethod
    def update_dashboard_status(db: Session, auth: AuthContext, *, status_value: str, last_active_time: datetime | None) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)

        normalized_status = status_value.strip().lower()
        if normalized_status not in {"online", "offline"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tracker status")

        device = TrackerService._get_or_create_dashboard_device(db, user=auth.user, employee=employee)
        session = TrackerService._find_active_session(db, str(device.id))
        if session is None:
            return {"message": "No active tracker session found"}

        ping_time = TrackerService._normalize_datetime(last_active_time) or TrackerService._utcnow()
        session.is_online = normalized_status == "online"
        session.last_active_at = ping_time
        session.last_heartbeat = ping_time
        device.last_seen_at = ping_time
        db.commit()
        return {"message": "Tracker status updated", "status": normalized_status}

    @staticmethod
    def offline_sync(db: Session, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        handlers = {
            "start_session": TrackerService.start_session,
            "end_session": TrackerService.end_session,
            "idle_start": TrackerService.idle_start,
            "idle_end": TrackerService.idle_end,
            "heartbeat": TrackerService.heartbeat,
        }
        handler = handlers.get(event_type)
        if handler is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported offline tracker event")
        return handler(db, payload)

    @staticmethod
    def monitor(db: Session, auth: AuthContext) -> dict[str, object]:
        TrackerService._mark_stale_sessions_offline(db)

        if auth.access.is_super_admin or "*" in auth.access.permission_keys or "attendance.view.all" in auth.access.permission_keys:
            scope_employee_ids = None
            scope_user_ids = None
        elif "attendance.view.team" in auth.access.permission_keys:
            scope_employee_ids = UserScopeService.get_team_employee_ids(db, auth, include_self=True)
            scope_user_ids = {str(auth.user.id)}
        else:
            employee_id = UserScopeService.current_employee_id(auth)
            scope_employee_ids = {employee_id} if employee_id else set()
            scope_user_ids = {str(auth.user.id)}

        session_stmt = select(TrackerSession).order_by(
            TrackerSession.started_at.desc(),
            TrackerSession.created_at.desc(),
        )
        if scope_employee_ids is not None:
            scope_conditions = []
            if scope_employee_ids:
                scope_conditions.append(TrackerSession.employee_id.in_(scope_employee_ids))
            if scope_user_ids:
                scope_conditions.append(TrackerSession.user_id.in_(scope_user_ids))
            if not scope_conditions:
                return {"items": [], "total": 0}
            session_stmt = session_stmt.where(or_(*scope_conditions))

        sessions = db.execute(session_stmt).scalars().all()
        if not sessions:
            return {"items": [], "total": 0}

        device_ids = {str(item.device_id) for item in sessions}
        employee_ids = {str(item.employee_id) for item in sessions if item.employee_id}
        user_ids = {str(item.user_id) for item in sessions if item.user_id}
        devices = db.execute(select(Device).where(Device.id.in_(device_ids))).scalars().all() if device_ids else []
        employees = db.execute(
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department))
            .where(Employee.id.in_(employee_ids))
        ).scalars().all() if employee_ids else []
        users = db.execute(
            select(User)
            .options(joinedload(User.role))
            .where(User.id.in_(user_ids))
        ).scalars().all() if user_ids else []

        device_map = {str(item.id): item for item in devices}
        employee_map = {str(item.id): item for item in employees}
        user_map = {str(item.id): item for item in users}

        latest_heartbeat_rows = db.execute(
            select(TrackerHeartbeat)
            .where(TrackerHeartbeat.device_id.in_(device_ids))
            .order_by(TrackerHeartbeat.heartbeat_at.desc())
        ).scalars().all() if device_ids else []
        latest_heartbeat_by_device: dict[str, TrackerHeartbeat] = {}
        for row in latest_heartbeat_rows:
            latest_heartbeat_by_device.setdefault(str(row.device_id), row)

        items: list[dict[str, object]] = []
        now = TrackerService._utcnow()
        for session in sessions:
            employee = employee_map.get(str(session.employee_id)) if session.employee_id else None
            user = user_map.get(str(session.user_id)) if session.user_id else (employee.user if employee else None)
            if employee is None and user is None:
                continue

            device = device_map.get(str(session.device_id))
            heartbeat = latest_heartbeat_by_device.get(str(session.device_id))
            last_active_at = TrackerService._resolve_last_active(session, device, heartbeat.heartbeat_at if heartbeat else None)
            current_status = TrackerService._current_status(session, last_active_at=last_active_at, now=now)
            items.append(
                TrackerService._serialize_monitor_row(
                    session,
                    employee,
                    user,
                    device,
                    last_active_at=last_active_at,
                    current_status=current_status,
                )
            )

        return {"items": items, "total": len(items)}
