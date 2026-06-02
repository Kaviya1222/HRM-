from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceAuditLog, AttendanceCorrection, AttendanceDailySummary, AttendanceLog
from app.models.auth import User
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, EmployeeStatus, LeaveRequestStatus
from app.models.leave import LeaveRequest
from app.models.utility import AuditLog
from app.services.settings_service import SettingsService
from app.services.tracker_service import TrackerService
from app.services.user_scope_service import UserScopeService


class AttendanceService:
    SESSION_ONLINE = "online"
    SESSION_OFFLINE = "offline"

    @staticmethod
    def _time_parts(value: dict[str, object], default_hour: int, default_minute: int) -> tuple[int, int]:
        try:
            hour = int(value.get("hour", default_hour))
            minute = int(value.get("minute", default_minute))
        except (TypeError, ValueError):
            return default_hour, default_minute
        return min(max(hour, 0), 23), min(max(minute, 0), 59)

    @staticmethod
    def _thresholds(db: Session) -> dict[str, int]:
        check_in_start = SettingsService.get_object_setting(db, "attendance.start_time", {"hour": 9, "minute": 30})
        late_entry_range = SettingsService.get_object_setting(
            db,
            "attendance.late_entry_range",
            {"start_hour": 9, "start_minute": 45, "end_hour": 13, "end_minute": 0},
        )
        half_day_range = SettingsService.get_object_setting(
            db,
            "attendance.half_day_range",
            {"start_hour": 13, "start_minute": 1, "end_hour": 18, "end_minute": 30},
        )
        start_hour, start_minute = AttendanceService._time_parts(check_in_start, 9, 30)
        late_start_hour, late_start_minute = AttendanceService._time_parts(
            {"hour": late_entry_range.get("start_hour"), "minute": late_entry_range.get("start_minute")},
            9,
            45,
        )
        late_end_hour, late_end_minute = AttendanceService._time_parts(
            {"hour": late_entry_range.get("end_hour"), "minute": late_entry_range.get("end_minute")},
            13,
            0,
        )
        half_start_hour, half_start_minute = AttendanceService._time_parts(
            {"hour": half_day_range.get("start_hour"), "minute": half_day_range.get("start_minute")},
            13,
            1,
        )
        half_end_hour, half_end_minute = AttendanceService._time_parts(
            {"hour": half_day_range.get("end_hour"), "minute": half_day_range.get("end_minute")},
            18,
            30,
        )
        return {
            "workday_start_hour": start_hour,
            "workday_start_minute": start_minute,
            "late_start_hour": late_start_hour,
            "late_start_minute": late_start_minute,
            "late_end_hour": late_end_hour,
            "late_end_minute": late_end_minute,
            "half_day_start_hour": half_start_hour,
            "half_day_start_minute": half_start_minute,
            "half_day_end_hour": half_end_hour,
            "half_day_end_minute": half_end_minute,
        }

    @staticmethod
    def _date_range(start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _approved_leave_for_date(db: Session, employee_id: str, target_date: date) -> LeaveRequest | None:
        return db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == employee_id,
                LeaveRequest.status == LeaveRequestStatus.APPROVED.value,
                LeaveRequest.start_date <= target_date,
                LeaveRequest.end_date >= target_date,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _employee_query():
        return (
            select(Employee)
            .options(joinedload(Employee.user), joinedload(Employee.department), joinedload(Employee.designation))
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.is_deleted.is_(False),
                Employee.status == EmployeeStatus.ACTIVE.value,
                User.is_active.is_(True),
            )
        )

    @staticmethod
    def _serialize_item(
        *,
        employee: Employee,
        attendance_date: date,
        log: AttendanceLog | None = None,
        status_override: str | None = None,
        leave_request_id: str | None = None,
        sessions: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        user = employee.user
        employee_name = user.full_name if user and user.full_name else employee.employee_code
        department_name = employee.department.name if employee.department else None
        designation_name = employee.designation.name if employee.designation else None
        return {
            "id": log.id if log else None,
            "employee_id": employee.id,
            "employee_name": employee_name,
            "employee_code": employee.employee_code,
            "department_name": department_name,
            "designation_name": designation_name,
            "attendance_date": attendance_date,
            "check_in_at": log.check_in_at if log else None,
            "check_out_at": log.check_out_at if log else None,
            "work_minutes": log.work_minutes if log else 0,
            "work_seconds": log.work_seconds if log else 0,
            "status": status_override or (log.status if log else AttendanceStatus.ABSENT.value),
            "is_late": log.is_late if log else False,
            "source": log.source if log else "system",
            "corrected_at": log.corrected_at if log else None,
            "leave_request_id": leave_request_id,
            "sessions": sessions or ([] if log is None else [AttendanceService._serialize_session(log)]),
        }

    @staticmethod
    def _serialize_session(log: AttendanceLog) -> dict[str, object]:
        work_seconds = (
            AttendanceService._calculate_work_seconds(log.check_in_at, log.check_out_at)
            if log.check_in_at and log.check_out_at
            else int(log.work_seconds or 0)
        )
        return {
            "id": log.id,
            "check_in_at": log.check_in_at,
            "check_out_at": log.check_out_at,
            "work_minutes": work_seconds // 60,
            "work_seconds": work_seconds,
            "status": log.status,
            "is_late": log.is_late,
        }

    @staticmethod
    def _serialize_user_item(
        *,
        user: User,
        attendance_date: date,
        log: AttendanceLog | None = None,
        status_override: str | None = None,
        sessions: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "id": log.id if log else None,
            "employee_id": None,
            "user_id": user.id,
            "employee_name": user.full_name or user.email,
            "employee_code": None,
            "department_name": None,
            "designation_name": None,
            "attendance_date": attendance_date,
            "check_in_at": log.check_in_at if log else None,
            "check_out_at": log.check_out_at if log else None,
            "work_minutes": log.work_minutes if log else 0,
            "work_seconds": log.work_seconds if log else 0,
            "status": status_override or (log.status if log else AttendanceStatus.ABSENT.value),
            "is_late": log.is_late if log else False,
            "source": log.source if log else "web",
            "corrected_at": log.corrected_at if log else None,
            "leave_request_id": None,
            "sessions": sessions or ([] if log is None else [AttendanceService._serialize_session(log)]),
        }

    @staticmethod
    def _today_log_for_employee(db: Session, *, employee_id: str, today: date) -> AttendanceLog | None:
        return db.execute(
            select(AttendanceLog)
            .where(AttendanceLog.employee_id == employee_id, AttendanceLog.attendance_date == today)
            .order_by(AttendanceLog.updated_at.desc(), AttendanceLog.created_at.desc())
        ).scalars().first()

    @staticmethod
    def _today_logs_for_employee(db: Session, *, employee_id: str, today: date) -> list[AttendanceLog]:
        return db.execute(
            select(AttendanceLog)
            .where(AttendanceLog.employee_id == employee_id, AttendanceLog.attendance_date == today)
            .order_by(AttendanceLog.check_in_at.asc(), AttendanceLog.created_at.asc())
        ).scalars().all()

    @staticmethod
    def _open_today_log_for_employee(db: Session, *, employee_id: str, today: date) -> AttendanceLog | None:
        return db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == today,
                AttendanceLog.check_in_at.is_not(None),
                AttendanceLog.check_out_at.is_(None),
            )
            .order_by(AttendanceLog.created_at.desc())
        ).scalars().first()

    @staticmethod
    def _today_log_for_user(db: Session, *, user_id: str, today: date) -> AttendanceLog | None:
        return db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.user_id == user_id,
                AttendanceLog.employee_id.is_(None),
                AttendanceLog.attendance_date == today,
            )
            .order_by(AttendanceLog.updated_at.desc(), AttendanceLog.created_at.desc())
        ).scalars().first()

    @staticmethod
    def _today_logs_for_user(db: Session, *, user_id: str, today: date) -> list[AttendanceLog]:
        return db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.user_id == user_id,
                AttendanceLog.employee_id.is_(None),
                AttendanceLog.attendance_date == today,
            )
            .order_by(AttendanceLog.check_in_at.asc(), AttendanceLog.created_at.asc())
        ).scalars().all()

    @staticmethod
    def _open_today_log_for_user(db: Session, *, user_id: str, today: date) -> AttendanceLog | None:
        return db.execute(
            select(AttendanceLog)
            .where(
                AttendanceLog.user_id == user_id,
                AttendanceLog.employee_id.is_(None),
                AttendanceLog.attendance_date == today,
                AttendanceLog.check_in_at.is_not(None),
                AttendanceLog.check_out_at.is_(None),
            )
            .order_by(AttendanceLog.created_at.desc())
        ).scalars().first()

    @staticmethod
    def _calculate_work_minutes(check_in_at: datetime, check_out_at: datetime) -> int:
        delta = check_out_at - check_in_at
        return max(int(delta.total_seconds() // 60), 0)

    @staticmethod
    def _calculate_work_seconds(check_in_at: datetime, check_out_at: datetime) -> int:
        delta = check_out_at - check_in_at
        return max(int(delta.total_seconds()), 0)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value

    @staticmethod
    def _total_work_minutes_for_employee_date(db: Session, *, employee_id: str, attendance_date: date) -> int:
        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == attendance_date,
            )
        ).scalars().all()
        return sum(AttendanceService._session_work_seconds(log) // 60 for log in logs)

    @staticmethod
    def _total_work_seconds_for_employee_date(db: Session, *, employee_id: str, attendance_date: date) -> int:
        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == attendance_date,
            )
        ).scalars().all()
        return sum(AttendanceService._session_work_seconds(log) for log in logs)

    @staticmethod
    def _session_work_seconds(log: AttendanceLog) -> int:
        if log.check_in_at and log.check_out_at:
            return AttendanceService._calculate_work_seconds(log.check_in_at, log.check_out_at)
        return int(log.work_seconds or 0)

    @staticmethod
    def _serialize_grouped_item(*, employee: Employee, attendance_date: date, logs: list[AttendanceLog], thresholds: dict[str, int] | None = None) -> dict[str, object]:
        ordered_logs = sorted(logs, key=lambda item: (item.check_in_at or item.created_at, item.created_at))
        latest_log = max(ordered_logs, key=lambda item: (item.updated_at, item.created_at))
        check_in_values = [item.check_in_at for item in ordered_logs if item.check_in_at]
        check_out_values = [item.check_out_at for item in ordered_logs if item.check_out_at]
        total_work_seconds = sum(AttendanceService._session_work_seconds(item) for item in ordered_logs)
        total_work_minutes = total_work_seconds // 60
        first_check_in = min(check_in_values) if check_in_values else None
        status_value = AttendanceService._status_after_check_in(first_check_in, thresholds) if thresholds and first_check_in else latest_log.status

        item = AttendanceService._serialize_item(
            employee=employee,
            attendance_date=attendance_date,
            log=latest_log,
            status_override=status_value,
            sessions=[AttendanceService._serialize_session(item) for item in ordered_logs],
        )
        item["check_in_at"] = first_check_in or latest_log.check_in_at
        item["check_out_at"] = max(check_out_values) if check_out_values else None
        item["work_minutes"] = total_work_minutes
        item["work_seconds"] = total_work_seconds
        item["is_late"] = any(item.is_late for item in ordered_logs)
        return item

    @staticmethod
    def _time_for_date(target: datetime, hour_key: str, minute_key: str, thresholds: dict[str, int]) -> datetime:
        return datetime.combine(
            target.date(),
            time(thresholds[hour_key], thresholds[minute_key], tzinfo=target.tzinfo),
        )

    @staticmethod
    def _derive_status(work_minutes: int, thresholds: dict[str, int], *, check_in_at: datetime | None = None) -> str:
        return AttendanceService._status_after_check_in(check_in_at, thresholds)

    @staticmethod
    def _is_late(check_in_at: datetime, thresholds: dict[str, int]) -> bool:
        late_start = AttendanceService._time_for_date(check_in_at, "late_start_hour", "late_start_minute", thresholds)
        late_end = AttendanceService._time_for_date(check_in_at, "late_end_hour", "late_end_minute", thresholds)
        return late_start <= check_in_at <= late_end

    @staticmethod
    def _is_after_late_cutoff(check_in_at: datetime, thresholds: dict[str, int]) -> bool:
        half_day_end = AttendanceService._time_for_date(check_in_at, "half_day_end_hour", "half_day_end_minute", thresholds)
        return check_in_at > half_day_end

    @staticmethod
    def _status_after_check_in(check_in_at: datetime | None, thresholds: dict[str, int]) -> str:
        if check_in_at is None:
            return AttendanceStatus.ABSENT.value
        start_time = AttendanceService._time_for_date(check_in_at, "workday_start_hour", "workday_start_minute", thresholds)
        late_start = AttendanceService._time_for_date(check_in_at, "late_start_hour", "late_start_minute", thresholds)
        late_end = AttendanceService._time_for_date(check_in_at, "late_end_hour", "late_end_minute", thresholds)
        half_day_start = AttendanceService._time_for_date(check_in_at, "half_day_start_hour", "half_day_start_minute", thresholds)
        half_day_end = AttendanceService._time_for_date(check_in_at, "half_day_end_hour", "half_day_end_minute", thresholds)

        if check_in_at <= start_time or check_in_at < late_start:
            return AttendanceStatus.PRESENT.value
        if late_start <= check_in_at <= late_end:
            return AttendanceStatus.PRESENT.value
        if half_day_start <= check_in_at <= half_day_end:
            return AttendanceStatus.HALF_DAY.value
        if late_end < check_in_at < half_day_start:
            return AttendanceStatus.HALF_DAY.value
        return AttendanceStatus.ABSENT.value

    @staticmethod
    def _upsert_daily_summary(
        db: Session,
        *,
        employee_id: str,
        summary_date: date,
        status: str,
        work_minutes: int,
        work_seconds: int | None = None,
        leave_request_id: str | None = None,
    ) -> AttendanceDailySummary:
        normalized_work_seconds = work_minutes * 60 if work_seconds is None else work_seconds
        summary = db.execute(
            select(AttendanceDailySummary).where(
                AttendanceDailySummary.employee_id == employee_id,
                AttendanceDailySummary.summary_date == summary_date,
            )
        ).scalar_one_or_none()

        if summary is None:
            summary = AttendanceDailySummary(
                employee_id=employee_id,
                summary_date=summary_date,
                status=status,
                work_minutes=work_minutes,
                work_seconds=normalized_work_seconds,
                leave_request_id=leave_request_id,
            )
            db.add(summary)
        else:
            summary.status = status
            summary.work_minutes = work_minutes
            summary.work_seconds = normalized_work_seconds
            summary.leave_request_id = leave_request_id
        return summary

    @staticmethod
    def _attendance_scope(db: Session, auth: AuthContext) -> set[str] | None:
        return UserScopeService.resolve_employee_scope(
            db,
            auth,
            own_permission="attendance.view.own",
            team_permission="attendance.view.team",
            all_permission="attendance.view.all",
        )

    @staticmethod
    def calculate_today_statistics(db: Session, *, active_employee_ids: list[str], today: date) -> dict[str, int | float]:
        active_count = len(active_employee_ids)
        if not active_employee_ids:
            return {
                "present": 0,
                "late": 0,
                "half_day": 0,
                "absent": 0,
                "leave": 0,
                "attended": 0,
                "attendance_percentage": 0.0,
            }

        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id.in_(active_employee_ids),
                AttendanceLog.attendance_date == today,
            )
        ).scalars().all()
        latest_logs: dict[str, AttendanceLog] = {}
        for log in logs:
            employee_id = str(log.employee_id)
            existing_log = latest_logs.get(employee_id)
            if existing_log is None or (log.updated_at, log.created_at) >= (existing_log.updated_at, existing_log.created_at):
                latest_logs[employee_id] = log

        approved_today_leaves = db.execute(
            select(LeaveRequest).where(
                LeaveRequest.employee_id.in_(active_employee_ids),
                LeaveRequest.status == LeaveRequestStatus.APPROVED.value,
                LeaveRequest.start_date <= today,
                LeaveRequest.end_date >= today,
            )
        ).scalars().all()
        leave_employee_ids = {str(item.employee_id) for item in approved_today_leaves}
        thresholds = AttendanceService._thresholds(db)

        present_count = 0
        late_count = 0
        half_day_count = 0
        for log in latest_logs.values():
            employee_id = str(log.employee_id)
            status_value = log.status
            if log.check_in_at:
                status_value = AttendanceService._status_after_check_in(log.check_in_at, thresholds)
            if status_value == AttendanceStatus.LEAVE.value:
                leave_employee_ids.add(employee_id)
                continue
            if employee_id in leave_employee_ids:
                continue
            if status_value == AttendanceStatus.PRESENT.value and log.is_late:
                late_count += 1
            elif status_value == AttendanceStatus.PRESENT.value:
                present_count += 1
            elif status_value == AttendanceStatus.HALF_DAY.value:
                half_day_count += 1

        leave_count = len(leave_employee_ids)
        absent_count = max(active_count - present_count - leave_count - late_count, 0)
        attended_count = present_count + late_count + half_day_count
        attendance_percentage = round((attended_count / active_count) * 100, 1) if active_count else 0.0

        return {
            "present": present_count,
            "late": late_count,
            "half_day": half_day_count,
            "absent": absent_count,
            "leave": leave_count,
            "attended": attended_count,
            "attendance_percentage": attendance_percentage,
        }

    @staticmethod
    def get_today_statistics(db: Session, auth: AuthContext) -> dict[str, object]:
        scope_ids = AttendanceService._attendance_scope(db, auth)
        employee_stmt = AttendanceService._employee_query()
        if scope_ids is not None:
            if not scope_ids:
                return {
                    "today": date.today(),
                    "counts": AttendanceService.calculate_today_statistics(db, active_employee_ids=[], today=date.today()),
                }
            employee_stmt = employee_stmt.where(Employee.id.in_(scope_ids))

        employees = db.execute(employee_stmt).scalars().all()
        active_employee_ids = [str(employee.id) for employee in employees]
        today = date.today()
        return {
            "today": today,
            "counts": AttendanceService.calculate_today_statistics(db, active_employee_ids=active_employee_ids, today=today),
        }

    @staticmethod
    def get_meta(db: Session, auth: AuthContext) -> dict[str, object]:
        scope_ids = AttendanceService._attendance_scope(db, auth)
        stmt = AttendanceService._employee_query()
        if scope_ids is not None:
            stmt = stmt.where(Employee.id.in_(scope_ids))
        employees = db.execute(stmt.order_by(Employee.created_at.desc())).scalars().all()
        return {
            "thresholds": AttendanceService._thresholds(db),
            "employees": [
                {
                    "id": employee.id,
                    "employee_code": employee.employee_code,
                    "full_name": employee.user.full_name if employee.user else employee.employee_code,
                    "department_name": employee.department.name if employee.department else None,
                    "designation_name": employee.designation.name if employee.designation else None,
                }
                for employee in employees
            ],
        }

    @staticmethod
    def get_today_overview(db: Session, auth: AuthContext) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)
        today = date.today()
        can_check_in_by_permission = auth.access.is_super_admin or "attendance.check_in" in auth.access.permission_keys
        can_check_out_by_permission = auth.access.is_super_admin or "attendance.check_out" in auth.access.permission_keys
        if employee is None:
            logs = AttendanceService._today_logs_for_user(db, user_id=str(auth.user.id), today=today)
            latest_log = AttendanceService._today_log_for_user(db, user_id=str(auth.user.id), today=today)
            open_log = AttendanceService._open_today_log_for_user(db, user_id=str(auth.user.id), today=today)
            log = open_log or latest_log
            thresholds = AttendanceService._thresholds(db)
            status_value = AttendanceService._status_after_check_in(log.check_in_at, thresholds) if log and log.check_in_at else AttendanceStatus.ABSENT.value
            return {
                "today": today,
                "thresholds": thresholds,
                "status": status_value,
                "log": AttendanceService._serialize_user_item(
                    user=auth.user,
                    attendance_date=today,
                    log=log,
                    status_override=status_value,
                    sessions=[AttendanceService._serialize_session(item) for item in logs],
                ),
                "can_check_in": can_check_in_by_permission and latest_log is None,
                "can_check_out": can_check_out_by_permission and open_log is not None,
            }

        leave_request = AttendanceService._approved_leave_for_date(db, str(employee.id), today)
        logs = AttendanceService._today_logs_for_employee(db, employee_id=str(employee.id), today=today)
        latest_log = AttendanceService._today_log_for_employee(db, employee_id=str(employee.id), today=today)
        open_log = AttendanceService._open_today_log_for_employee(db, employee_id=str(employee.id), today=today)
        log = open_log or latest_log
        thresholds = AttendanceService._thresholds(db)
        status_value = (
            AttendanceStatus.LEAVE.value
            if leave_request
            else (AttendanceService._status_after_check_in(log.check_in_at, thresholds) if log and log.check_in_at else AttendanceStatus.ABSENT.value)
        )
        return {
            "today": today,
            "thresholds": thresholds,
            "status": status_value,
            "log": AttendanceService._serialize_item(
                employee=employee,
                attendance_date=today,
                log=log,
                status_override=status_value,
                sessions=[AttendanceService._serialize_session(item) for item in logs],
            ),
            "can_check_in": can_check_in_by_permission and leave_request is None and latest_log is None,
            "can_check_out": can_check_out_by_permission and leave_request is None and open_log is not None,
        }

    @staticmethod
    def check_in(db: Session, auth: AuthContext, payload: dict[str, object] | None = None) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)
        today = date.today()
        if employee and AttendanceService._approved_leave_for_date(db, str(employee.id), today):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Approved leave exists for today")

        open_log = (
            AttendanceService._open_today_log_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._open_today_log_for_user(db, user_id=str(auth.user.id), today=today)
        )
        if open_log is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already checked in. Please check out first.",
            )
        latest_log = (
            AttendanceService._today_log_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._today_log_for_user(db, user_id=str(auth.user.id), today=today)
        )
        if latest_log is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Attendance already exists for today.",
            )

        payload = payload or {}
        now = AttendanceService._normalize_datetime(payload.get("check_in_at")) or datetime.now(UTC).replace(tzinfo=None)
        thresholds = AttendanceService._thresholds(db)
        semantic_status = AttendanceService._status_after_check_in(now, thresholds)
        log = AttendanceLog(
            employee_id=employee.id if employee else None,
            user_id=auth.user.id if employee is None else None,
            attendance_date=today,
            check_in_at=now,
            status=AttendanceService.SESSION_ONLINE,
            is_late=AttendanceService._is_late(now, thresholds),
            source="web",
        )
        db.add(log)

        if employee:
            db.flush()
            current_work_minutes = AttendanceService._total_work_minutes_for_employee_date(db, employee_id=str(employee.id), attendance_date=today)
            current_work_seconds = AttendanceService._total_work_seconds_for_employee_date(db, employee_id=str(employee.id), attendance_date=today)
            AttendanceService._upsert_daily_summary(
                db,
                employee_id=str(employee.id),
                summary_date=today,
                status=semantic_status,
                work_minutes=current_work_minutes,
                work_seconds=current_work_seconds,
            )
        db.commit()
        db.refresh(log)
        TrackerService.sync_dashboard_check_in(db, auth, log.check_in_at)
        logs = (
            AttendanceService._today_logs_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._today_logs_for_user(db, user_id=str(auth.user.id), today=today)
        )
        serialized_log = (
            AttendanceService._serialize_item(
                employee=employee,
                attendance_date=today,
                log=log,
                status_override=semantic_status,
                sessions=[AttendanceService._serialize_session(item) for item in logs],
            )
            if employee
            else AttendanceService._serialize_user_item(
                user=auth.user,
                attendance_date=today,
                log=log,
                status_override=semantic_status,
                sessions=[AttendanceService._serialize_session(item) for item in logs],
            )
        )
        return {"message": "Checked in successfully", "log": serialized_log}

    @staticmethod
    def check_out(db: Session, auth: AuthContext, payload: dict[str, object] | None = None) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)
        today = date.today()
        log = (
            AttendanceService._open_today_log_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._open_today_log_for_user(db, user_id=str(auth.user.id), today=today)
        )
        latest_log = (
            AttendanceService._today_log_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._today_log_for_user(db, user_id=str(auth.user.id), today=today)
        )
        if log is None or log.check_in_at is None:
            if latest_log and latest_log.check_in_at and latest_log.check_out_at:
                TrackerService.sync_dashboard_check_out(db, auth, latest_log.check_out_at)
                serialized_log = (
                    AttendanceService._serialize_item(employee=employee, attendance_date=today, log=latest_log)
                    if employee
                    else AttendanceService._serialize_user_item(user=auth.user, attendance_date=today, log=latest_log)
                )
                return {"message": "Already checked out today", "log": serialized_log}
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Check-out cannot happen before check-in")
        if log.check_out_at is not None:
            TrackerService.sync_dashboard_check_out(db, auth, log.check_out_at)
            serialized_log = (
                AttendanceService._serialize_item(employee=employee, attendance_date=today, log=log)
                if employee
                else AttendanceService._serialize_user_item(user=auth.user, attendance_date=today, log=log)
            )
            return {"message": "Already checked out today", "log": serialized_log}

        payload = payload or {}
        requested_check_in = AttendanceService._normalize_datetime(payload.get("check_in_at"))
        requested_check_out = AttendanceService._normalize_datetime(payload.get("check_out_at"))
        now = requested_check_out or datetime.now(UTC).replace(tzinfo=None)
        if requested_check_in is not None:
            log.check_in_at = requested_check_in
        if now < log.check_in_at:
            now = log.check_in_at

        payload_work_seconds = payload.get("elapsed_seconds")
        work_seconds = (
            max(int(payload_work_seconds), 0)
            if payload_work_seconds is not None
            else AttendanceService._calculate_work_seconds(log.check_in_at, now)
        )
        work_minutes = work_seconds // 60
        thresholds = AttendanceService._thresholds(db)
        status_value = AttendanceService._derive_status(work_minutes, thresholds, check_in_at=log.check_in_at)
        log.check_out_at = now
        log.work_minutes = work_minutes
        log.work_seconds = work_seconds
        log.status = AttendanceService.SESSION_OFFLINE
        log.is_late = AttendanceService._is_late(log.check_in_at, thresholds)
        db.flush()

        if employee:
            total_work_minutes = AttendanceService._total_work_minutes_for_employee_date(db, employee_id=str(employee.id), attendance_date=today)
            total_work_seconds = AttendanceService._total_work_seconds_for_employee_date(db, employee_id=str(employee.id), attendance_date=today)
            AttendanceService._upsert_daily_summary(
                db,
                employee_id=str(employee.id),
                summary_date=today,
                status=AttendanceService._derive_status(total_work_minutes, thresholds, check_in_at=log.check_in_at),
                work_minutes=total_work_minutes,
                work_seconds=total_work_seconds,
            )
        db.commit()
        db.refresh(log)
        TrackerService.sync_dashboard_check_out(db, auth, log.check_out_at or now)
        logs = (
            AttendanceService._today_logs_for_employee(db, employee_id=str(employee.id), today=today)
            if employee
            else AttendanceService._today_logs_for_user(db, user_id=str(auth.user.id), today=today)
        )
        serialized_log = (
            AttendanceService._serialize_item(
                employee=employee,
                attendance_date=today,
                log=log,
                status_override=status_value,
                sessions=[AttendanceService._serialize_session(item) for item in logs],
            )
            if employee
            else AttendanceService._serialize_user_item(
                user=auth.user,
                attendance_date=today,
                log=log,
                status_override=status_value,
                sessions=[AttendanceService._serialize_session(item) for item in logs],
            )
        )
        return {"message": "Checked out successfully", "log": serialized_log}

    @staticmethod
    def list_attendance(
        db: Session,
        auth: AuthContext,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        employee_id: str | None = None,
    ) -> dict[str, object]:
        today = date.today()
        start_date = start_date or today.replace(day=1)
        end_date = end_date or today

        scope_ids = AttendanceService._attendance_scope(db, auth)
        if employee_id:
            UserScopeService.ensure_employee_in_scope(employee_id, scope_ids)
            scope_ids = {employee_id}

        employee_stmt = AttendanceService._employee_query()
        if scope_ids is not None:
            if not scope_ids:
                return {"items": [], "total": 0}
            employee_stmt = employee_stmt.where(Employee.id.in_(scope_ids))
        employees = db.execute(employee_stmt).scalars().all()
        employee_map = {str(employee.id): employee for employee in employees}

        log_stmt = select(AttendanceLog).where(AttendanceLog.attendance_date >= start_date, AttendanceLog.attendance_date <= end_date)
        if scope_ids is not None:
            log_stmt = log_stmt.where(AttendanceLog.employee_id.in_(scope_ids))
        logs = db.execute(log_stmt).scalars().all()

        log_map: dict[tuple[str, date], AttendanceLog] = {}
        logs_by_key: dict[tuple[str, date], list[AttendanceLog]] = {}
        for log in logs:
            log_key = (str(log.employee_id), log.attendance_date)
            logs_by_key.setdefault(log_key, []).append(log)
            existing_log = log_map.get(log_key)
            if existing_log is None or (log.updated_at, log.created_at) >= (existing_log.updated_at, existing_log.created_at):
                log_map[log_key] = log

        items = [
            AttendanceService._serialize_grouped_item(
                employee=employee_map[employee_id],
                attendance_date=attendance_date,
                logs=logs_by_key[(employee_id, attendance_date)],
                thresholds=AttendanceService._thresholds(db),
            )
            for (employee_id, attendance_date), log in log_map.items()
            if employee_id in employee_map
        ]

        leave_stmt = select(LeaveRequest).where(
            LeaveRequest.status == LeaveRequestStatus.APPROVED.value,
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if scope_ids is not None:
            leave_stmt = leave_stmt.where(LeaveRequest.employee_id.in_(scope_ids))
        leave_requests = db.execute(leave_stmt).scalars().all()

        for leave_request in leave_requests:
            employee = employee_map.get(str(leave_request.employee_id))
            if employee is None:
                continue
            for day in AttendanceService._date_range(max(start_date, leave_request.start_date), min(end_date, leave_request.end_date)):
                if (str(leave_request.employee_id), day) in log_map:
                    continue
                items.append(
                    AttendanceService._serialize_item(
                        employee=employee,
                        attendance_date=day,
                        status_override=AttendanceStatus.LEAVE.value,
                        leave_request_id=str(leave_request.id),
                    )
                )

        if start_date == end_date:
            placeholder_date = start_date
        elif start_date <= today <= end_date:
            placeholder_date = today
        else:
            placeholder_date = None
        leave_lookup = {
            (str(leave_request.employee_id), day): leave_request
            for leave_request in leave_requests
            for day in AttendanceService._date_range(max(start_date, leave_request.start_date), min(end_date, leave_request.end_date))
        }

        if placeholder_date is not None:
            for employee in employees:
                employee_id = str(employee.id)
                if (employee_id, placeholder_date) in log_map:
                    continue

                matching_leave = leave_lookup.get((employee_id, placeholder_date))
                items.append(
                    AttendanceService._serialize_item(
                        employee=employee,
                        attendance_date=placeholder_date,
                        status_override=AttendanceStatus.LEAVE.value if matching_leave else AttendanceStatus.ABSENT.value,
                        leave_request_id=str(matching_leave.id) if matching_leave else None,
                    )
                )

        deduped_items: dict[tuple[str, date], dict[str, object]] = {}
        for item in items:
            item_key = (str(item["employee_id"]), item["attendance_date"])
            existing_item = deduped_items.get(item_key)
            if existing_item is None:
                deduped_items[item_key] = item
                continue

            if item["id"] and not existing_item["id"]:
                deduped_items[item_key] = item
                continue

            if item["status"] == AttendanceStatus.LEAVE.value and existing_item["status"] == AttendanceStatus.ABSENT.value:
                deduped_items[item_key] = item

        items = list(deduped_items.values())
        items.sort(key=lambda item: (item["attendance_date"], item["employee_name"]), reverse=True)
        return {"items": items, "total": len(items)}

    @staticmethod
    def update_manual_attendance(db: Session, auth: AuthContext, *, payload: dict[str, object]) -> dict[str, object]:
        employee_id = str(payload.get("employee_id", "")).strip()
        attendance_date = payload.get("attendance_date")
        selected_status = str(payload.get("status", "")).strip()

        if not employee_id or not isinstance(attendance_date, date):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee and attendance date are required")

        scope_ids = AttendanceService._attendance_scope(db, auth)
        UserScopeService.ensure_employee_in_scope(employee_id, scope_ids)

        employee = db.execute(AttendanceService._employee_query().where(Employee.id == employee_id)).scalar_one_or_none()
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

        status_map = {
            "present": (AttendanceStatus.PRESENT.value, 0, False),
            "late_come": (AttendanceStatus.PRESENT.value, 0, True),
            "half_day": (AttendanceStatus.HALF_DAY.value, 0, False),
            "absent": (AttendanceStatus.ABSENT.value, 0, False),
            "leave": (AttendanceStatus.LEAVE.value, 0, False),
        }
        if selected_status not in status_map:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid attendance status")

        status_value, work_minutes, is_late = status_map[selected_status]
        work_seconds = work_minutes * 60
        logs = db.execute(
            select(AttendanceLog).where(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.attendance_date == attendance_date,
            ).order_by(AttendanceLog.updated_at.desc(), AttendanceLog.created_at.desc())
        ).scalars().all()
        log = logs[0] if logs else None
        old_data = jsonable_encoder(
            AttendanceService._serialize_item(employee=employee, attendance_date=attendance_date, log=log)
            if log
            else AttendanceService._serialize_item(employee=employee, attendance_date=attendance_date)
        )

        if log is None:
            log = AttendanceLog(
                employee_id=employee_id,
                attendance_date=attendance_date,
                status=status_value,
                work_minutes=work_minutes,
                work_seconds=work_seconds,
                is_late=is_late,
                source="manual",
                corrected_by_user_id=auth.user.id,
                corrected_at=datetime.now(UTC),
            )
            db.add(log)
            db.flush()
        else:
            log.status = status_value
            log.work_minutes = work_minutes
            log.work_seconds = work_seconds
            log.is_late = is_late
            log.source = "manual"
            log.corrected_by_user_id = auth.user.id
            log.corrected_at = datetime.now(UTC)

        for duplicate_log in logs[1:]:
            db.delete(duplicate_log)

        if selected_status in {"absent", "half_day", "leave"}:
            log.check_in_at = None
            log.check_out_at = None

        AttendanceService._upsert_daily_summary(
            db,
            employee_id=employee_id,
            summary_date=attendance_date,
            status=status_value,
            work_minutes=work_minutes,
            work_seconds=work_seconds,
        )

        after_data = jsonable_encoder({
            "employee_id": employee_id,
            "attendance_date": attendance_date,
            "status": status_value,
            "manual_status": selected_status,
            "work_minutes": work_minutes,
            "work_seconds": work_seconds,
            "is_late": is_late,
        })
        db.add(
            AttendanceAuditLog(
                attendance_log_id=log.id,
                changed_by_user_id=auth.user.id,
                action="attendance.manual_update",
                before_data=old_data,
                after_data=after_data,
            )
        )
        db.add(
            AuditLog(
                actor_user_id=auth.user.id,
                entity_type="attendance",
                entity_id=str(log.id),
                action="attendance.manual_update",
                before_data=old_data,
                after_data=after_data,
            )
        )

        db.commit()
        db.refresh(log)
        return {
            "message": "Attendance updated successfully",
            "log": AttendanceService._serialize_item(employee=employee, attendance_date=attendance_date, log=log),
        }

    @staticmethod
    def correct_attendance(db: Session, auth: AuthContext, *, log_id: str, payload: dict[str, object]) -> dict[str, object]:
        log = db.get(AttendanceLog, log_id)
        if log is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance log not found")

        scope_ids = AttendanceService._attendance_scope(db, auth)
        UserScopeService.ensure_employee_in_scope(str(log.employee_id), scope_ids)

        employee = db.execute(AttendanceService._employee_query().where(Employee.id == log.employee_id)).scalar_one()
        old_data = jsonable_encoder(AttendanceService._serialize_item(employee=employee, attendance_date=log.attendance_date, log=log))

        new_check_in = payload["check_in_at"] if "check_in_at" in payload else log.check_in_at
        new_check_out = payload["check_out_at"] if "check_out_at" in payload else log.check_out_at
        reason = str(payload.get("reason", "")).strip()

        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reason is required for attendance correction")
        if new_check_in is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Check-in time is required for correction")
        if new_check_out is not None and new_check_out < new_check_in:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrected check-out cannot be before check-in")

        thresholds = AttendanceService._thresholds(db)
        work_seconds = AttendanceService._calculate_work_seconds(new_check_in, new_check_out) if new_check_out else 0
        work_minutes = work_seconds // 60
        status_value = (
            AttendanceService._derive_status(work_minutes, thresholds, check_in_at=new_check_in)
            if new_check_out
            else AttendanceService._status_after_check_in(new_check_in, thresholds)
        )

        log.check_in_at = new_check_in
        log.check_out_at = new_check_out
        log.work_minutes = work_minutes
        log.work_seconds = work_seconds
        log.status = status_value
        log.is_late = AttendanceService._is_late(new_check_in, thresholds)
        log.corrected_by_user_id = auth.user.id
        log.corrected_at = datetime.now(UTC)

        AttendanceService._upsert_daily_summary(
            db,
            employee_id=str(log.employee_id),
            summary_date=log.attendance_date,
            status=status_value,
            work_minutes=work_minutes,
            work_seconds=work_seconds,
        )

        db.add(
            AttendanceCorrection(
                attendance_log_id=log.id,
                requested_by_user_id=auth.user.id,
                approved_by_user_id=auth.user.id,
                reason=reason,
                old_data=old_data,
                new_data=jsonable_encoder({
                    "check_in_at": new_check_in,
                    "check_out_at": new_check_out,
                    "work_minutes": work_minutes,
                    "status": status_value,
                }),
                status="approved",
            )
        )
        db.add(
            AttendanceAuditLog(
                attendance_log_id=log.id,
                changed_by_user_id=auth.user.id,
                action="attendance.corrected",
                before_data=old_data,
                after_data=jsonable_encoder({
                    "check_in_at": new_check_in,
                    "check_out_at": new_check_out,
                    "work_minutes": work_minutes,
                    "status": status_value,
                }),
            )
        )
        db.add(
            AuditLog(
                actor_user_id=auth.user.id,
                entity_type="attendance",
                entity_id=str(log.id),
                action="attendance.corrected",
                before_data=old_data,
                after_data=jsonable_encoder({
                    "check_in_at": new_check_in,
                    "check_out_at": new_check_out,
                    "work_minutes": work_minutes,
                    "status": status_value,
                }),
            )
        )

        db.commit()
        db.refresh(log)
        return {"message": "Attendance corrected successfully", "log": AttendanceService._serialize_item(employee=employee, attendance_date=log.attendance_date, log=log)}
