from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import ROLE_DISPLAY_NAMES, RoleCode
from app.core.security import get_password_hash
from app.models.attendance import AttendanceDailySummary, AttendanceLog, AttendanceRule
from app.models.auth import Permission, Role, RolePermission, User
from app.models.employee import Department, Designation, Employee, ReportingManager
from app.models.enums import AttendanceStatus, DeviceStatus, LeaveRequestStatus, PayrollRunStatus, TrackerSessionStatus, UserStatus
from app.models.leave import LeaveApproval, LeaveBalance, LeaveRequest, LeaveType
from app.models.payroll import PayrollRun, Payslip, SalaryStructure
from app.models.tracker import Device, TrackerHeartbeat, TrackerIdleLog, TrackerSession
from app.models.utility import AppSetting, Holiday, Notification
from app.permissions.catalog import DEFAULT_ROLE_PERMISSION_KEYS, PERMISSION_CATALOG, role_hierarchy_seed
from app.services.settings_service import DEFAULT_BRANDING


DEFAULT_APP_SETTINGS = [
    {
        "key": "branding.organization_name",
        "category": "branding",
        "name": "Organization Name",
        "description": "Primary organization name shown across the application shell.",
        "value_type": "json",
        "value_json": {"text": DEFAULT_BRANDING["organization_name"]},
        "is_public": True,
    },
    {
        "key": "branding.portal_tagline",
        "category": "branding",
        "name": "Portal Tagline",
        "description": "Short supporting label shown below the organization name.",
        "value_type": "json",
        "value_json": {"text": DEFAULT_BRANDING["tagline"]},
        "is_public": True,
    },
    {
        "key": "branding.logo",
        "category": "branding",
        "name": "Organization Logo",
        "description": "Logo image and fallback text used in the application shell.",
        "value_type": "json",
        "value_json": {
            "text": DEFAULT_BRANDING["logo_text"],
            "data_url": DEFAULT_BRANDING["logo_data_url"],
        },
        "is_public": True,
    },
    {
        "key": "attendance.late_mark_after_minutes",
        "category": "attendance",
        "name": "Late Mark Threshold",
        "description": "Minutes after shift start to mark a late entry.",
        "value_type": "json",
        "value_json": {"minutes": 15},
        "is_public": False,
    },
    {
        "key": "attendance.half_day_min_minutes",
        "category": "attendance",
        "name": "Half Day Threshold",
        "description": "Minimum worked minutes required to avoid half-day status.",
        "value_type": "json",
        "value_json": {"minutes": 240},
        "is_public": False,
    },
    {
        "key": "tracker.idle_threshold_minutes",
        "category": "tracker",
        "name": "Tracker Idle Threshold",
        "description": "Idle threshold in minutes for tracker clients.",
        "value_type": "json",
        "value_json": {"minutes": 5},
        "is_public": False,
    },
    {
        "key": "tracker.heartbeat_interval_seconds",
        "category": "tracker",
        "name": "Tracker Heartbeat Interval",
        "description": "Heartbeat sync interval for tracker clients.",
        "value_type": "json",
        "value_json": {"seconds": 60},
        "is_public": False,
    },
    {
        "key": "attendance.workday_start",
        "category": "attendance",
        "name": "Workday Start Time",
        "description": "Nominal workday start time used for late mark calculation.",
        "value_type": "json",
        "value_json": {"hour": 9, "minute": 0},
        "is_public": False,
    },
    {
        "key": "tracker.shared_token",
        "category": "tracker",
        "name": "Tracker Shared Token",
        "description": "Shared bearer token used by tracker clients in development or controlled deployments.",
        "value_type": "json",
        "value_json": {"token": settings.tracker_shared_token},
        "is_public": False,
    },
]

DEFAULT_DEPARTMENTS = [
    {"name": "Engineering", "code": "ENG", "description": "Engineering and product delivery teams."},
    {"name": "Product", "code": "PRD", "description": "Product management and roadmap planning."},
    {"name": "Sales", "code": "SLS", "description": "Sales operations and revenue teams."},
    {"name": "Human Resources", "code": "HR", "description": "Human resources operations and people support."},
    {"name": "Finance", "code": "FIN", "description": "Finance, payroll, and accounting operations."},
    {"name": "Operations", "code": "OPS", "description": "Operations, administration, and coordination."},
]

DEFAULT_DESIGNATIONS = [
    {"name": "Software Engineer", "code": "SWE", "description": "Engineering team member."},
    {"name": "Team Lead", "code": "TL", "description": "Team leadership role."},
    {"name": "Product Manager", "code": "PM", "description": "Product strategy and roadmap ownership."},
    {"name": "Sales Executive", "code": "SE", "description": "Sales pipeline and client relationship role."},
    {"name": "HR Executive", "code": "HRE", "description": "Human resources specialist."},
    {"name": "Operations Executive", "code": "OPE", "description": "Operations and administration specialist."},
]

DEFAULT_LEAVE_TYPES = [
    {"name": "Casual Leave", "code": "CL", "annual_allowance": 12, "description": "General personal leave."},
    {"name": "Sick Leave", "code": "SL", "annual_allowance": 8, "description": "Medical or sick leave."},
    {"name": "Earned Leave", "code": "EL", "annual_allowance": 15, "description": "Accrued earned leave."},
]

DEMO_DEFAULT_PASSWORD = "DemoUser@123"


def _shift_month(base_date: date, months: int) -> date:
    total_month_index = (base_date.year * 12 + (base_date.month - 1)) + months
    year = total_month_index // 12
    month = total_month_index % 12 + 1
    return date(year, month, 1)


def _safe_month_date(month_start: date, preferred_day: int) -> date:
    day = min(preferred_day, calendar.monthrange(month_start.year, month_start.month)[1])
    return month_start.replace(day=day)


def _combine_utc(target_date: date, hour: int, minute: int) -> datetime:
    return datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=UTC)


def _date_range(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _inclusive_days(start_date: date, end_date: date) -> Decimal:
    return Decimal((end_date - start_date).days + 1)


def _sum_components(payload: dict | None) -> Decimal:
    total = Decimal("0")
    for value in (payload or {}).values():
        total += Decimal(str(value))
    return total


def _seed_demo_data(db: Session, *, roles_by_code: dict[str, Role], super_admin_user: User) -> None:
    if not settings.seed_demo_data or settings.environment.lower() == "production":
        return
    if db.execute(select(Employee.id).limit(1)).scalar_one_or_none() is not None:
        return

    today = date.today()
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    current_month_start = today.replace(day=1)
    previous_month_start = _shift_month(current_month_start, -1)

    departments_by_code = {item.code: item for item in db.execute(select(Department)).scalars().all()}
    designations_by_code = {item.code: item for item in db.execute(select(Designation)).scalars().all()}
    leave_types_by_code = {item.code: item for item in db.execute(select(LeaveType)).scalars().all()}

    demo_profiles = [
        {
            "employee_code": "ADM001",
            "email": "admin.demo@hrm.local",
            "first_name": "Aiden",
            "last_name": "Stone",
            "role_code": RoleCode.ADMIN.value,
            "department_code": "OPS",
            "designation_code": "OPE",
            "joining_offset_days": 720,
            "date_of_birth": date(1990, 5, 14),
            "phone_number": "+91-90000-10001",
            "address": "Operations HQ, Bengaluru",
            "base_salary": Decimal("95000"),
            "is_active": True,
        },
        {
            "employee_code": "HR001",
            "email": "hr.demo@hrm.local",
            "first_name": "Hannah",
            "last_name": "Reed",
            "role_code": RoleCode.HR.value,
            "department_code": "HR",
            "designation_code": "HRE",
            "joining_offset_days": 640,
            "date_of_birth": date(1992, 8, 21),
            "phone_number": "+91-90000-10002",
            "address": "People Operations, Hyderabad",
            "base_salary": Decimal("78000"),
            "is_active": True,
        },
        {
            "employee_code": "TL001",
            "email": "tl.demo@hrm.local",
            "first_name": "Liam",
            "last_name": "Carter",
            "role_code": RoleCode.TL.value,
            "department_code": "ENG",
            "designation_code": "TL",
            "joining_offset_days": 540,
            "date_of_birth": date(1989, 11, 3),
            "phone_number": "+91-90000-10003",
            "address": "Engineering Hub, Pune",
            "base_salary": Decimal("110000"),
            "is_active": True,
        },
        {
            "employee_code": "EMP001",
            "email": "noah.bennett@hrm.local",
            "first_name": "Noah",
            "last_name": "Bennett",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "ENG",
            "designation_code": "SWE",
            "joining_offset_days": 360,
            "date_of_birth": date(1995, 2, 18),
            "phone_number": "+91-90000-10004",
            "address": "Koramangala, Bengaluru",
            "base_salary": Decimal("62000"),
            "is_active": True,
        },
        {
            "employee_code": "EMP002",
            "email": "mia.chen@hrm.local",
            "first_name": "Mia",
            "last_name": "Chen",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "ENG",
            "designation_code": "SWE",
            "joining_offset_days": 290,
            "date_of_birth": date(1996, 6, 7),
            "phone_number": "+91-90000-10005",
            "address": "Whitefield, Bengaluru",
            "base_salary": Decimal("60000"),
            "is_active": True,
        },
        {
            "employee_code": "EMP003",
            "email": "priya.kapoor@hrm.local",
            "first_name": "Priya",
            "last_name": "Kapoor",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "ENG",
            "designation_code": "SWE",
            "joining_offset_days": 210,
            "date_of_birth": date(1997, 1, 29),
            "phone_number": "+91-90000-10006",
            "address": "Electronic City, Bengaluru",
            "base_salary": Decimal("64000"),
            "is_active": True,
        },
        {
            "employee_code": "EMP004",
            "email": "daniel.brooks@hrm.local",
            "first_name": "Daniel",
            "last_name": "Brooks",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "ENG",
            "designation_code": "SWE",
            "joining_offset_days": 180,
            "date_of_birth": date(1994, 4, 13),
            "phone_number": "+91-90000-10007",
            "address": "HSR Layout, Bengaluru",
            "base_salary": Decimal("58000"),
            "is_active": True,
        },
        {
            "employee_code": "FIN001",
            "email": "oliver.price@hrm.local",
            "first_name": "Oliver",
            "last_name": "Price",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "FIN",
            "designation_code": "OPE",
            "joining_offset_days": 415,
            "date_of_birth": date(1991, 10, 22),
            "phone_number": "+91-90000-10009",
            "address": "Indiranagar, Bengaluru",
            "base_salary": Decimal("72000"),
            "is_active": True,
        },
        {
            "employee_code": "PM001",
            "email": "ava.morgan@hrm.local",
            "first_name": "Ava",
            "last_name": "Morgan",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "PRD",
            "designation_code": "PM",
            "joining_offset_days": 330,
            "date_of_birth": date(1992, 12, 5),
            "phone_number": "+91-90000-10010",
            "address": "Baner, Pune",
            "base_salary": Decimal("88000"),
            "is_active": True,
        },
        {
            "employee_code": "SAL001",
            "email": "ethan.hughes@hrm.local",
            "first_name": "Ethan",
            "last_name": "Hughes",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "SLS",
            "designation_code": "SE",
            "joining_offset_days": 260,
            "date_of_birth": date(1991, 7, 17),
            "phone_number": "+91-90000-10011",
            "address": "Madhapur, Hyderabad",
            "base_salary": Decimal("57000"),
            "is_active": True,
        },
        {
            "employee_code": "EMP005",
            "email": "emma.gray@hrm.local",
            "first_name": "Emma",
            "last_name": "Gray",
            "role_code": RoleCode.EMPLOYEE.value,
            "department_code": "FIN",
            "designation_code": "OPE",
            "joining_offset_days": 480,
            "date_of_birth": date(1993, 9, 9),
            "phone_number": "+91-90000-10008",
            "address": "Jayanagar, Bengaluru",
            "base_salary": Decimal("55000"),
            "is_active": False,
        },
    ]

    users_by_code: dict[str, User] = {}
    employees_by_code: dict[str, Employee] = {}

    for profile in demo_profiles:
        user = User(
            email=profile["email"],
            password_hash=get_password_hash(DEMO_DEFAULT_PASSWORD),
            first_name=profile["first_name"],
            last_name=profile["last_name"],
            role_id=roles_by_code[profile["role_code"]].id,
            is_active=bool(profile["is_active"]),
            status=UserStatus.ACTIVE.value if profile["is_active"] else UserStatus.INACTIVE.value,
            last_login_at=now - timedelta(hours=2),
        )
        db.add(user)
        db.flush()

        employee = Employee(
            user_id=user.id,
            employee_code=profile["employee_code"],
            department_id=departments_by_code[profile["department_code"]].id,
            designation_id=designations_by_code[profile["designation_code"]].id,
            joining_date=today - timedelta(days=int(profile["joining_offset_days"])),
            date_of_birth=profile["date_of_birth"],
            phone_number=profile["phone_number"],
            address=profile["address"],
            status="active" if profile["is_active"] else "inactive",
            base_salary=profile["base_salary"],
            is_billable=profile["department_code"] == "ENG",
        )
        db.add(employee)
        db.flush()

        users_by_code[profile["employee_code"]] = user
        employees_by_code[profile["employee_code"]] = employee

    manager_links = {
        "HR001": "ADM001",
        "TL001": "ADM001",
        "EMP001": "TL001",
        "EMP002": "TL001",
        "EMP003": "TL001",
        "EMP004": "TL001",
        "FIN001": "ADM001",
        "PM001": "ADM001",
        "SAL001": "ADM001",
        "EMP005": "ADM001",
    }
    for employee_code, manager_code in manager_links.items():
        employee = employees_by_code[employee_code]
        manager = employees_by_code[manager_code]
        employee.manager_id = manager.id
        db.add(
            ReportingManager(
                employee_id=employee.id,
                manager_id=manager.id,
                start_date=employee.joining_date or today,
                is_primary=True,
            )
        )

    leave_request_specs = [
        {
            "employee_code": "EMP002",
            "leave_type_code": "SL",
            "start_date": today - timedelta(days=1),
            "end_date": today,
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Medical recovery",
            "approver_code": "HR001",
            "remarks": "Approved based on medical intimation.",
        },
        {
            "employee_code": "EMP001",
            "leave_type_code": "CL",
            "start_date": _safe_month_date(_shift_month(current_month_start, -1), 6),
            "end_date": _safe_month_date(_shift_month(current_month_start, -1), 7),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Family function",
            "approver_code": "HR001",
            "remarks": "Planned leave approved.",
        },
        {
            "employee_code": "EMP004",
            "leave_type_code": "EL",
            "start_date": _safe_month_date(_shift_month(current_month_start, -2), 10),
            "end_date": _safe_month_date(_shift_month(current_month_start, -2), 12),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Vacation travel",
            "approver_code": "ADM001",
            "remarks": "Approved against earned leave balance.",
        },
        {
            "employee_code": "HR001",
            "leave_type_code": "CL",
            "start_date": _safe_month_date(_shift_month(current_month_start, -3), 9),
            "end_date": _safe_month_date(_shift_month(current_month_start, -3), 9),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Personal work",
            "approver_code": "ADM001",
            "remarks": "Approved.",
        },
        {
            "employee_code": "ADM001",
            "leave_type_code": "SL",
            "start_date": _safe_month_date(_shift_month(current_month_start, -4), 14),
            "end_date": _safe_month_date(_shift_month(current_month_start, -4), 14),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Health appointment",
            "approver_code": "HR001",
            "remarks": "Approved.",
        },
        {
            "employee_code": "TL001",
            "leave_type_code": "EL",
            "start_date": _safe_month_date(_shift_month(current_month_start, -5), 16),
            "end_date": _safe_month_date(_shift_month(current_month_start, -5), 17),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Travel leave",
            "approver_code": "ADM001",
            "remarks": "Approved.",
        },
        {
            "employee_code": "FIN001",
            "leave_type_code": "CL",
            "start_date": _safe_month_date(current_month_start, 8),
            "end_date": _safe_month_date(current_month_start, 8),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Banking and personal documentation",
            "approver_code": "ADM001",
            "remarks": "Approved for a planned personal day.",
        },
        {
            "employee_code": "PM001",
            "leave_type_code": "EL",
            "start_date": _safe_month_date(current_month_start, 12),
            "end_date": _safe_month_date(current_month_start, 13),
            "status": LeaveRequestStatus.APPROVED.value,
            "reason": "Product conference travel",
            "approver_code": "ADM001",
            "remarks": "Approved against earned leave.",
        },
        {
            "employee_code": "EMP003",
            "leave_type_code": "CL",
            "start_date": today + timedelta(days=2),
            "end_date": today + timedelta(days=3),
            "status": LeaveRequestStatus.PENDING.value,
            "reason": "Family visit",
            "approver_code": "HR001",
            "remarks": None,
        },
        {
            "employee_code": "SAL001",
            "leave_type_code": "CL",
            "start_date": today + timedelta(days=5),
            "end_date": today + timedelta(days=5),
            "status": LeaveRequestStatus.PENDING.value,
            "reason": "Client-side personal errand",
            "approver_code": "HR001",
            "remarks": None,
        },
        {
            "employee_code": "EMP005",
            "leave_type_code": "SL",
            "start_date": _safe_month_date(previous_month_start, 11),
            "end_date": _safe_month_date(previous_month_start, 11),
            "status": LeaveRequestStatus.REJECTED.value,
            "reason": "Insufficient documentation",
            "approver_code": "HR001",
            "remarks": "Rejected due to missing supporting note.",
        },
    ]

    leave_request_day_map: dict[tuple[str, date], str] = {}
    approved_usage: dict[tuple[str, str, int], Decimal] = {}
    created_leave_requests: list[tuple[dict[str, object], LeaveRequest]] = []

    for index, spec in enumerate(leave_request_specs, start=1):
        leave_request = LeaveRequest(
            employee_id=employees_by_code[spec["employee_code"]].id,
            leave_type_id=leave_types_by_code[spec["leave_type_code"]].id,
            start_date=spec["start_date"],
            end_date=spec["end_date"],
            total_days=_inclusive_days(spec["start_date"], spec["end_date"]),
            reason=spec["reason"],
            status=spec["status"],
            requested_at=now - timedelta(days=15 - index),
        )
        db.add(leave_request)
        db.flush()

        created_leave_requests.append((spec, leave_request))

        if spec["status"] in [LeaveRequestStatus.APPROVED.value, LeaveRequestStatus.REJECTED.value]:
            db.add(
                LeaveApproval(
                    leave_request_id=leave_request.id,
                    approver_user_id=users_by_code[spec["approver_code"]].id,
                    decision=spec["status"],
                    remarks=spec["remarks"],
                    acted_at=leave_request.requested_at + timedelta(hours=6),
                )
            )

        if spec["status"] == LeaveRequestStatus.APPROVED.value:
            approved_usage[
                (
                    str(leave_request.employee_id),
                    str(leave_request.leave_type_id),
                    leave_request.start_date.year,
                )
            ] = approved_usage.get(
                (
                    str(leave_request.employee_id),
                    str(leave_request.leave_type_id),
                    leave_request.start_date.year,
                ),
                Decimal("0"),
            ) + Decimal(str(leave_request.total_days))

            current_range_start = max(leave_request.start_date, current_month_start)
            current_range_end = min(leave_request.end_date, today)
            if current_range_start <= current_range_end:
                for leave_day in _date_range(current_range_start, current_range_end):
                    leave_request_day_map[(spec["employee_code"], leave_day)] = str(leave_request.id)

    for employee in employees_by_code.values():
        for leave_type in leave_types_by_code.values():
            opening_balance = Decimal(str(leave_type.annual_allowance))
            used_days = approved_usage.get((str(employee.id), str(leave_type.id), today.year), Decimal("0"))
            remaining_days = max(opening_balance - used_days, Decimal("0"))
            db.add(
                LeaveBalance(
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=today.year,
                    opening_balance=opening_balance,
                    used_days=used_days,
                    remaining_days=remaining_days,
                )
            )

    working_days: list[date] = []
    for target_date in _date_range(current_month_start, today):
        if target_date.weekday() < 5 or target_date == today:
            working_days.append(target_date)

    def working_day(index: int) -> date:
        if not working_days:
            return today
        return working_days[min(index, len(working_days) - 1)]

    current_month_leave_days: dict[str, set[date]] = {code: set() for code in employees_by_code}
    for (employee_code, leave_day), _leave_request_id in leave_request_day_map.items():
        current_month_leave_days.setdefault(employee_code, set()).add(leave_day)

    late_days = {
        "ADM001": {today},
        "HR001": {working_day(2)},
        "TL001": {working_day(4)},
        "EMP001": {today},
        "FIN001": {working_day(1)},
        "SAL001": {working_day(5)},
    }
    half_day_days = {
        "EMP004": {working_day(3)},
        "PM001": {working_day(7)},
    }
    absent_days = {
        "EMP003": {today},
        "EMP004": {working_day(6)},
        "SAL001": {working_day(2)},
    }

    attendance_counters: dict[str, dict[str, int]] = {
        code: {
            "present_days": 0,
            "half_days": 0,
            "leave_days": 0,
            "absent_days": 0,
            "working_days": len(working_days),
        }
        for code, employee in employees_by_code.items()
        if employee.status == "active"
    }

    for employee_code, employee in employees_by_code.items():
        if employee.status != "active":
            continue

        for attendance_day in working_days:
            if attendance_day in current_month_leave_days.get(employee_code, set()):
                attendance_counters[employee_code]["leave_days"] += 1
                db.add(
                    AttendanceDailySummary(
                        employee_id=employee.id,
                        summary_date=attendance_day,
                        status=AttendanceStatus.LEAVE.value,
                        work_minutes=0,
                        leave_request_id=leave_request_day_map.get((employee_code, attendance_day)),
                    )
                )
                continue

            if attendance_day in absent_days.get(employee_code, set()):
                attendance_counters[employee_code]["absent_days"] += 1
                continue

            is_late = attendance_day in late_days.get(employee_code, set())
            is_half_day = attendance_day in half_day_days.get(employee_code, set())
            check_in_at = _combine_utc(attendance_day, 9, 28 if is_late else 6)
            check_out_at = _combine_utc(attendance_day, 14, 5) if is_half_day else _combine_utc(attendance_day, 18, 12)
            work_minutes = int((check_out_at - check_in_at).total_seconds() // 60)
            status_value = AttendanceStatus.HALF_DAY.value if is_half_day else AttendanceStatus.PRESENT.value

            db.add(
                AttendanceLog(
                    employee_id=employee.id,
                    attendance_date=attendance_day,
                    check_in_at=check_in_at,
                    check_out_at=check_out_at,
                    work_minutes=work_minutes,
                    status=status_value,
                    is_late=is_late,
                    source="seed",
                )
            )
            db.add(
                AttendanceDailySummary(
                    employee_id=employee.id,
                    summary_date=attendance_day,
                    status=status_value,
                    work_minutes=work_minutes,
                )
            )

            if is_half_day:
                attendance_counters[employee_code]["half_days"] += 1
            else:
                attendance_counters[employee_code]["present_days"] += 1

    salary_structure_codes = ["ADM001", "HR001", "TL001", "EMP001", "EMP002", "EMP004", "FIN001", "PM001", "SAL001"]
    salary_structures_by_code: dict[str, SalaryStructure] = {}
    for employee_code in salary_structure_codes:
        employee = employees_by_code[employee_code]
        special_allowance = Decimal("10000") if employee_code in ["ADM001", "HR001", "TL001"] else Decimal("6500")
        pf_deduction = Decimal("2800") if employee_code in ["ADM001", "HR001", "TL001"] else Decimal("2000")
        structure = SalaryStructure(
            employee_id=employee.id,
            grade_name="Management" if employee_code in ["ADM001", "HR001", "TL001"] else "Engineering",
            basic_salary=employee.base_salary or Decimal("0"),
            allowances={
                "hra": float((employee.base_salary or Decimal("0")) * Decimal("0.22")),
                "special": float(special_allowance),
            },
            deductions={
                "pf": float(pf_deduction),
                "professional_tax": 200,
            },
            effective_from=current_month_start - timedelta(days=90),
            effective_to=None,
        )
        db.add(structure)
        db.flush()
        salary_structures_by_code[employee_code] = structure

    previous_run = PayrollRun(
        period_month=previous_month_start.month,
        period_year=previous_month_start.year,
        status=PayrollRunStatus.COMPLETED.value,
        initiated_by_user_id=users_by_code["ADM001"].id,
        processed_at=now - timedelta(days=20),
    )
    current_run = PayrollRun(
        period_month=today.month,
        period_year=today.year,
        status=PayrollRunStatus.PROCESSING.value,
        initiated_by_user_id=users_by_code["ADM001"].id,
        processed_at=now - timedelta(days=2),
    )
    db.add(previous_run)
    db.add(current_run)
    db.flush()

    previous_paid_codes = list(salary_structure_codes)
    current_paid_codes = ["ADM001", "HR001", "TL001", "EMP001", "EMP002", "FIN001", "PM001", "SAL001"]

    for payroll_run, paid_codes in [(previous_run, previous_paid_codes), (current_run, current_paid_codes)]:
        for employee_code in paid_codes:
            structure = salary_structures_by_code[employee_code]
            gross_salary = Decimal(str(structure.basic_salary)) + _sum_components(structure.allowances)
            deduction_amount = _sum_components(structure.deductions)
            net_salary = gross_salary - deduction_amount
            attendance_summary = attendance_counters.get(employee_code, {
                "present_days": 20,
                "half_days": 0,
                "leave_days": 0,
                "absent_days": 0,
                "working_days": 20,
            })

            db.add(
                Payslip(
                    payroll_run_id=payroll_run.id,
                    employee_id=employees_by_code[employee_code].id,
                    gross_salary=gross_salary,
                    deduction_amount=deduction_amount,
                    net_salary=net_salary,
                    paid_days=Decimal(
                        str(
                            attendance_summary["present_days"]
                            + attendance_summary["leave_days"]
                            + (attendance_summary["half_days"] * 0.5)
                        )
                    ),
                    attendance_summary=attendance_summary,
                )
            )

    holiday_specs = [
        {"holiday_date": today + timedelta(days=3), "name": "Quarterly Town Hall", "is_optional": False},
        {"holiday_date": today + timedelta(days=5), "name": "Product Planning Workshop", "is_optional": False},
        {"holiday_date": today + timedelta(days=7), "name": "Sales Forecast Review", "is_optional": False},
        {"holiday_date": today + timedelta(days=10), "name": "Leadership Strategy Meet", "is_optional": False},
        {"holiday_date": today + timedelta(days=13), "name": "HR Policy Clinic", "is_optional": True},
        {"holiday_date": today + timedelta(days=17), "name": "Team Wellness Day", "is_optional": True},
    ]
    for holiday_spec in holiday_specs:
        db.add(Holiday(**holiday_spec))

    notification_specs = [
        {
            "title": "Leave approvals awaiting action",
            "message": "There are pending leave requests that require Super Admin visibility.",
            "notification_type": "approval",
            "hours_ago": 1,
            "is_read": False,
        },
        {
            "title": "Payroll run is in progress",
            "message": "Current month payroll is partially processed and still has pending payments.",
            "notification_type": "payroll",
            "hours_ago": 3,
            "is_read": False,
        },
        {
            "title": "Late arrivals detected",
            "message": "Multiple employees checked in after the configured late threshold today.",
            "notification_type": "attendance",
            "hours_ago": 5,
            "is_read": False,
        },
        {
            "title": "Tracker heartbeat stabilized",
            "message": "Live tracker devices are syncing correctly after the morning session.",
            "notification_type": "tracker",
            "hours_ago": 8,
            "is_read": True,
        },
        {
            "title": "Department events synced",
            "message": "Upcoming meetings and company events are available for dashboard widgets.",
            "notification_type": "calendar",
            "hours_ago": 10,
            "is_read": True,
        },
    ]
    for spec in notification_specs:
        created_at = now - timedelta(hours=spec["hours_ago"])
        db.add(
            Notification(
                user_id=super_admin_user.id,
                title=spec["title"],
                message=spec["message"],
                notification_type=spec["notification_type"],
                metadata_json={"seeded": True},
                target_url={
                    "approval": "/leave",
                    "payroll": "/payroll",
                    "calendar": "/calendar",
                    "attendance": "/attendance",
                    "tracker": "/tracker",
                }.get(spec["notification_type"], "/"),
                read_at=created_at + timedelta(minutes=25) if spec["is_read"] else None,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    tracker_specs = [
        {
            "employee_code": "EMP001",
            "device_uuid": "DEMO-DEVICE-EMP001",
            "device_name": "ENG-LAPTOP-01",
            "os_version": "Windows 11 Pro",
            "session_status": TrackerSessionStatus.ACTIVE.value,
            "started_at": now - timedelta(hours=3, minutes=20),
            "ended_at": None,
            "logout_time": None,
            "total_idle_minutes": 24,
            "is_online": True,
            "idle_logs": [],
            "heartbeats": [
                {"heartbeat_at": now - timedelta(minutes=7), "is_idle": False},
                {"heartbeat_at": now - timedelta(minutes=1), "is_idle": False},
            ],
        },
        {
            "employee_code": "EMP004",
            "device_uuid": "DEMO-DEVICE-EMP004",
            "device_name": "ENG-LAPTOP-04",
            "os_version": "Windows 11 Pro",
            "session_status": TrackerSessionStatus.ACTIVE.value,
            "started_at": now - timedelta(hours=2, minutes=50),
            "ended_at": None,
            "logout_time": None,
            "total_idle_minutes": 18,
            "is_online": True,
            "idle_logs": [
                {"idle_start_at": now - timedelta(minutes=12), "idle_end_at": None, "idle_minutes": 0},
            ],
            "heartbeats": [
                {"heartbeat_at": now - timedelta(minutes=6), "is_idle": True},
                {"heartbeat_at": now - timedelta(minutes=2), "is_idle": True},
            ],
        },
        {
            "employee_code": "TL001",
            "device_uuid": "DEMO-DEVICE-TL001",
            "device_name": "ENG-LEAD-WS-01",
            "os_version": "Windows 11 Enterprise",
            "session_status": TrackerSessionStatus.CLOSED.value,
            "started_at": now - timedelta(days=1, hours=1),
            "ended_at": now - timedelta(days=1) + timedelta(hours=8),
            "logout_time": now - timedelta(days=1) + timedelta(hours=8),
            "total_idle_minutes": 43,
            "is_online": False,
            "idle_logs": [
                {
                    "idle_start_at": now - timedelta(days=1) + timedelta(hours=4),
                    "idle_end_at": now - timedelta(days=1) + timedelta(hours=4, minutes=18),
                    "idle_minutes": 18,
                },
            ],
            "heartbeats": [
                {"heartbeat_at": now - timedelta(days=1) + timedelta(hours=7, minutes=35), "is_idle": False},
            ],
        },
    ]

    for tracker_spec in tracker_specs:
        employee = employees_by_code[tracker_spec["employee_code"]]
        device = Device(
            employee_id=employee.id,
            device_uuid=tracker_spec["device_uuid"],
            device_name=tracker_spec["device_name"],
            os_version=tracker_spec["os_version"],
            status=DeviceStatus.ACTIVE.value,
            last_seen_at=tracker_spec["heartbeats"][-1]["heartbeat_at"],
        )
        db.add(device)
        db.flush()

        session = TrackerSession(
            device_id=device.id,
            employee_id=employee.id,
            started_at=tracker_spec["started_at"],
            ended_at=tracker_spec["ended_at"],
            login_time=tracker_spec["started_at"],
            logout_time=tracker_spec["logout_time"],
            total_idle_minutes=tracker_spec["total_idle_minutes"],
            status=tracker_spec["session_status"],
            is_online=tracker_spec["is_online"],
            sync_state="synced",
        )
        db.add(session)
        db.flush()

        for idle_log in tracker_spec["idle_logs"]:
            db.add(
                TrackerIdleLog(
                    tracker_session_id=session.id,
                    idle_start_at=idle_log["idle_start_at"],
                    idle_end_at=idle_log["idle_end_at"],
                    idle_minutes=idle_log["idle_minutes"],
                )
            )

        for heartbeat in tracker_spec["heartbeats"]:
            db.add(
                TrackerHeartbeat(
                    device_id=device.id,
                    employee_id=employee.id,
                    tracker_session_id=session.id,
                    heartbeat_at=heartbeat["heartbeat_at"],
                    is_idle=heartbeat["is_idle"],
                    payload={"device_name": device.device_name},
                )
            )


def bootstrap_reference_data(db: Session) -> None:
    roles_by_code = {role.code: role for role in db.execute(select(Role)).scalars().all()}

    for item in role_hierarchy_seed():
        role = roles_by_code.get(item["code"])
        if role is None:
            role = Role(
                code=str(item["code"]),
                name=ROLE_DISPLAY_NAMES[RoleCode(str(item["code"]))],
                hierarchy_rank=int(item["hierarchy_rank"]),
                description=f"{ROLE_DISPLAY_NAMES[RoleCode(str(item['code']))]} system role",
                is_system=True,
            )
            db.add(role)
            roles_by_code[role.code] = role
        else:
            role.name = ROLE_DISPLAY_NAMES[RoleCode(role.code)]
            role.hierarchy_rank = int(item["hierarchy_rank"])
            role.is_system = True

    db.flush()

    permissions_by_key = {permission.key: permission for permission in db.execute(select(Permission)).scalars().all()}
    for item in PERMISSION_CATALOG:
        permission = permissions_by_key.get(item["key"])
        if permission is None:
            permission = Permission(**item)
            db.add(permission)
            permissions_by_key[permission.key] = permission
        else:
            permission.name = item["name"]
            permission.module = item["module"]
            permission.category = item["category"]
            permission.resource = item["resource"]
            permission.action = item["action"]
            permission.description = item["description"]

    db.flush()

    permission_id_by_key = {permission.key: permission.id for permission in permissions_by_key.values()}

    for role_code, role in roles_by_code.items():
        existing_role_permissions = {
            role_permission.permission_id: role_permission
            for role_permission in db.execute(select(RolePermission).where(RolePermission.role_id == role.id)).scalars().all()
        }
        default_keys = DEFAULT_ROLE_PERMISSION_KEYS.get(RoleCode(role_code), set())

        for permission_key, permission_id in permission_id_by_key.items():
            should_allow = permission_key in default_keys or role_code == RoleCode.SUPER_ADMIN.value
            existing_role_permission = existing_role_permissions.get(permission_id)
            if existing_role_permission is not None:
                if should_allow and not existing_role_permission.is_allowed:
                    existing_role_permission.is_allowed = True
                continue
            db.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=permission_id,
                    is_allowed=should_allow,
                )
            )

    existing_settings = set(db.execute(select(AppSetting.key)).scalars().all())
    for item in DEFAULT_APP_SETTINGS:
        if item["key"] not in existing_settings:
            db.add(AppSetting(**item))

    existing_departments = {department.code: department for department in db.execute(select(Department)).scalars().all()}
    for item in DEFAULT_DEPARTMENTS:
        department = existing_departments.get(item["code"])
        if department is None:
            db.add(Department(**item))
        elif department.is_deleted:
            department.is_deleted = False
            department.deleted_at = None

    existing_designations = {designation.code: designation for designation in db.execute(select(Designation)).scalars().all()}
    for item in DEFAULT_DESIGNATIONS:
        designation = existing_designations.get(item["code"])
        if designation is None:
            db.add(Designation(**item))
        elif designation.is_deleted:
            designation.is_deleted = False
            designation.deleted_at = None

    existing_leave_types = {leave_type.code: leave_type for leave_type in db.execute(select(LeaveType)).scalars().all()}
    for item in DEFAULT_LEAVE_TYPES:
        leave_type = existing_leave_types.get(item["code"])
        if leave_type is None:
            db.add(LeaveType(**item))

    attendance_rule = db.execute(select(AttendanceRule).where(AttendanceRule.is_active.is_(True))).scalar_one_or_none()
    if attendance_rule is None:
        db.add(
            AttendanceRule(
                name="Default Rule",
                late_mark_after_minutes=15,
                half_day_min_minutes=240,
                full_day_min_minutes=480,
                effective_from=date.today(),
                is_active=True,
            )
        )

    super_admin_role = roles_by_code[RoleCode.SUPER_ADMIN.value]
    super_admin_email = str(settings.initial_super_admin_email).lower()
    super_admin_user = db.execute(select(User).where(User.email == super_admin_email)).scalar_one_or_none()
    if super_admin_user is None:
        super_admin_user = User(
            email=super_admin_email,
            password_hash=get_password_hash(settings.initial_super_admin_password),
            first_name="System",
            last_name="Owner",
            role_id=super_admin_role.id,
            is_active=True,
            status="active",
            last_login_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.add(super_admin_user)
    else:
        super_admin_user.role_id = super_admin_role.id
        super_admin_user.is_active = True
        super_admin_user.status = "active"

    db.flush()
    _seed_demo_data(db, roles_by_code=roles_by_code, super_admin_user=super_admin_user)
    db.commit()
