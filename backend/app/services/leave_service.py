from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.models.attendance import AttendanceDailySummary, AttendanceLog
from app.models.auth import Role, User
from app.models.employee import Employee
from app.models.enums import AttendanceStatus, EmployeeStatus, LeaveRequestStatus
from app.models.leave import LeaveApproval, LeaveBalance, LeaveRequest, LeaveType
from app.services.email_service import EmailService
from app.services.notification_service import NotificationService
from app.services.user_scope_service import UserScopeService


class LeaveService:
    @staticmethod
    def _date_range(start_date: date, end_date: date):
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _calculate_total_days(start_date: date, end_date: date) -> Decimal:
        if end_date < start_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave end date cannot be before start date")
        return Decimal((end_date - start_date).days + 1)

    @staticmethod
    def _ensure_balances(db: Session, *, employee_id: str, year: int) -> list[LeaveBalance]:
        leave_types = db.execute(select(LeaveType).order_by(LeaveType.name.asc())).scalars().all()
        existing = {
            str(balance.leave_type_id): balance
            for balance in db.execute(
                select(LeaveBalance).where(LeaveBalance.employee_id == employee_id, LeaveBalance.year == year)
            ).scalars().all()
        }
        created_or_existing: list[LeaveBalance] = []
        for leave_type in leave_types:
            balance = existing.get(str(leave_type.id))
            if balance is None:
                balance = LeaveBalance(
                    employee_id=employee_id,
                    leave_type_id=leave_type.id,
                    year=year,
                    opening_balance=leave_type.annual_allowance,
                    used_days=Decimal("0"),
                    remaining_days=leave_type.annual_allowance,
                )
                db.add(balance)
            created_or_existing.append(balance)
        db.flush()
        return created_or_existing

    @staticmethod
    def initialize_leave_balances_for_employee(db: Session, employee_id: str) -> None:
        """Initialize leave balances for a newly created employee for the current year."""
        from datetime import datetime
        current_year = datetime.utcnow().year
        LeaveService._ensure_balances(db, employee_id=employee_id, year=current_year)

    @staticmethod
    def _scope(db: Session, auth: AuthContext) -> set[str] | None:
        return UserScopeService.resolve_employee_scope(
            db,
            auth,
            own_permission="leave.view.own",
            team_permission="leave.view.team",
            all_permission="leave.view.all",
        )

    @staticmethod
    def _serialize_balance(balance: LeaveBalance, leave_type_map: dict[str, LeaveType]) -> dict[str, object]:
        leave_type = leave_type_map[str(balance.leave_type_id)]
        return {
            "id": balance.id,
            "leave_type_id": balance.leave_type_id,
            "leave_type_name": leave_type.name,
            "leave_type_code": leave_type.code,
            "year": balance.year,
            "opening_balance": balance.opening_balance,
            "used_days": balance.used_days,
            "remaining_days": balance.remaining_days,
        }

    @staticmethod
    def _serialize_request(
        request: LeaveRequest,
        employee_map: dict[str, Employee],
        leave_type_map: dict[str, LeaveType],
        approval_map: dict[str, LeaveApproval],
    ) -> dict[str, object]:
        employee = employee_map.get(str(request.employee_id))
        user = employee.user if employee else None
        leave_type = leave_type_map[str(request.leave_type_id)]
        latest_approval = approval_map.get(str(request.id))
        return {
            "id": request.id,
            "employee_id": request.employee_id,
            "employee_name": user.full_name if user else None,
            "employee_code": employee.employee_code if employee else None,
            "leave_type_id": request.leave_type_id,
            "leave_type_name": leave_type.name,
            "leave_type_code": leave_type.code,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "total_days": request.total_days,
            "reason": request.reason,
            "status": request.status,
            "requested_at": request.requested_at,
            "approved_at": request.approved_at,
            "rejected_at": request.rejected_at,
            "remarks": request.remarks or (latest_approval.remarks if latest_approval else None),
        }

    @staticmethod
    def _pending_or_approved_overlap_exists(
        db: Session,
        *,
        employee_id: str,
        start_date: date,
        end_date: date,
        exclude_request_id: str | None = None,
    ) -> bool:
        stmt = select(LeaveRequest).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.status.in_([LeaveRequestStatus.PENDING.value, LeaveRequestStatus.APPROVED.value]),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
        if exclude_request_id is not None:
            stmt = stmt.where(LeaveRequest.id != exclude_request_id)
        return db.execute(stmt).scalar_one_or_none() is not None

    @staticmethod
    def _approver_user_ids(db: Session) -> list[str]:
        users = db.execute(
            select(User)
            .join(Role, User.role_id == Role.id)
            .where(User.is_active.is_(True), Role.code.in_(["super_admin", "admin", "hr"]))
        ).scalars().all()
        return [str(user.id) for user in users]

    @staticmethod
    def _send_leave_decision_email(
        *,
        employee: Employee,
        leave_type: LeaveType,
        leave_request: LeaveRequest,
        decision: str,
        remarks: str | None,
    ) -> tuple[bool, str | None]:
        employee_name = employee.user.full_name if employee.user else employee.employee_code
        status_label = "Approved" if decision == LeaveRequestStatus.APPROVED.value else "Rejected"
        remarks_label = "Remarks" if decision == LeaveRequestStatus.APPROVED.value else "Rejection reason / remarks"
        body_lines = [
            f"Hello {employee_name},",
            "",
            f"Your leave request has been {status_label.lower()}.",
            "",
            f"Employee: {employee_name}",
            f"Leave type: {leave_type.name}",
            f"Start date: {leave_request.start_date}",
            f"End date: {leave_request.end_date}",
            f"Total days: {leave_request.total_days}",
            f"Status: {status_label}",
        ]
        if remarks:
            body_lines.append(f"{remarks_label}: {remarks}")
        body_lines.extend(["", "Regards,", "HRM"])
        return EmailService.send_email(
            to_email=employee.user.email if employee.user else None,
            subject=f"Leave Request {status_label}",
            body="\n".join(body_lines),
        )

    @staticmethod
    def get_meta(db: Session, auth: AuthContext) -> dict[str, object]:
        employee = UserScopeService.current_employee(auth)
        leave_types = db.execute(select(LeaveType).order_by(LeaveType.name.asc())).scalars().all()
        leave_type_map = {str(item.id): item for item in leave_types}
        scope_ids = LeaveService._scope(db, auth)
        employee_stmt = (
            select(Employee)
            .options(joinedload(Employee.user))
            .join(User, Employee.user_id == User.id)
            .where(
                Employee.is_deleted.is_(False),
                Employee.status == EmployeeStatus.ACTIVE.value,
                User.is_active.is_(True),
            )
            .order_by(User.first_name.asc(), User.last_name.asc(), Employee.employee_code.asc())
        )
        if scope_ids is not None:
            if not scope_ids:
                employees = []
            else:
                employee_stmt = employee_stmt.where(Employee.id.in_(scope_ids))
                employees = db.execute(employee_stmt).scalars().unique().all()
        else:
            employees = db.execute(employee_stmt).scalars().unique().all()
        balances: list[dict[str, object]] = []
        if employee is not None:
            records = LeaveService._ensure_balances(db, employee_id=str(employee.id), year=date.today().year)
            balances = [LeaveService._serialize_balance(balance, leave_type_map) for balance in records]
            db.commit()
        return {
            "leave_types": [
                {"id": item.id, "name": item.name, "code": item.code, "annual_allowance": item.annual_allowance}
                for item in leave_types
            ],
            "employees": [
                {
                    "id": item.id,
                    "employee_code": item.employee_code,
                    "full_name": item.user.full_name if item.user and item.user.full_name else item.employee_code,
                }
                for item in employees
            ],
            "balances": balances,
        }

    @staticmethod
    def list_requests(
        db: Session,
        auth: AuthContext,
        *,
        status_filter: str | None = None,
        employee_id: str | None = None,
    ) -> dict[str, object]:
        scope_ids = LeaveService._scope(db, auth)
        if employee_id:
            UserScopeService.ensure_employee_in_scope(employee_id, scope_ids)
            scope_ids = {employee_id}

        stmt = select(LeaveRequest).order_by(LeaveRequest.requested_at.desc())
        if status_filter:
            stmt = stmt.where(LeaveRequest.status == status_filter)
        if scope_ids is not None:
            if not scope_ids:
                return {"items": [], "total": 0}
            stmt = stmt.where(LeaveRequest.employee_id.in_(scope_ids))

        requests = db.execute(stmt).scalars().all()
        employee_ids = {str(item.employee_id) for item in requests}
        employees = db.execute(
            select(Employee).options(joinedload(Employee.user)).where(Employee.id.in_(employee_ids))
        ).scalars().all() if employee_ids else []
        approvals = db.execute(
            select(LeaveApproval).where(LeaveApproval.leave_request_id.in_([item.id for item in requests]))
        ).scalars().all() if requests else []
        employee_map = {str(item.id): item for item in employees}
        leave_types = db.execute(select(LeaveType)).scalars().all()
        leave_type_map = {str(item.id): item for item in leave_types}
        approval_map: dict[str, LeaveApproval] = {}
        for approval in approvals:
            existing = approval_map.get(str(approval.leave_request_id))
            if existing is None or approval.acted_at > existing.acted_at:
                approval_map[str(approval.leave_request_id)] = approval

        items = [LeaveService._serialize_request(item, employee_map, leave_type_map, approval_map) for item in requests]
        return {"items": items, "total": len(items)}

    @staticmethod
    def apply_leave(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        employee_id = str(payload.get("employee_id") or "").strip()
        if employee_id:
            scope_ids = LeaveService._scope(db, auth)
            UserScopeService.ensure_employee_in_scope(employee_id, scope_ids)
            employee = db.execute(
                select(Employee).options(joinedload(Employee.user)).where(
                    Employee.id == employee_id,
                    Employee.is_deleted.is_(False),
                    Employee.status == EmployeeStatus.ACTIVE.value,
                )
            ).scalars().unique().first()
        else:
            employee = UserScopeService.current_employee(auth)

        if employee is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current user is not linked to an employee profile")

        reason = str(payload.get("reason") or payload.get("remarks") or "").strip()
        if not reason:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reason is required")

        leave_type_id = str(payload.get("leave_type_id") or "").strip()
        leave_type = db.get(LeaveType, leave_type_id) if leave_type_id else None
        if leave_type is None and payload.get("leave_type"):
            leave_type_value = str(payload.get("leave_type") or "").strip()
            leave_type = db.execute(
                select(LeaveType).where(
                    (LeaveType.name == leave_type_value) | (LeaveType.code == leave_type_value)
                )
            ).scalar_one_or_none()
        if leave_type is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found")

        total_days = LeaveService._calculate_total_days(payload["start_date"], payload["end_date"])
        if LeaveService._pending_or_approved_overlap_exists(
            db,
            employee_id=str(employee.id),
            start_date=payload["start_date"],
            end_date=payload["end_date"],
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Overlapping leave request already exists")

        leave_request = LeaveRequest(
            employee_id=employee.id,
            leave_type_id=leave_type.id,
            start_date=payload["start_date"],
            end_date=payload["end_date"],
            total_days=total_days,
            reason=reason,
            status=LeaveRequestStatus.PENDING.value,
            requested_at=datetime.now(UTC),
        )
        db.add(leave_request)
        db.flush()

        NotificationService.create_bulk_notifications(
            db,
            user_ids=LeaveService._approver_user_ids(db),
            title="New leave request submitted",
            message=f"{auth.user.full_name} requested {total_days} day(s) of {leave_type.name}.",
            notification_type="approval",
            metadata_json={"leave_request_id": str(leave_request.id)},
            related_id=leave_request.id,
            target_url="/leave",
        )
        db.commit()
        return {"message": "Leave request submitted successfully", "leave_request_id": leave_request.id}

    @staticmethod
    def decide_leave(db: Session, auth: AuthContext, *, leave_request_id: str, decision: str, remarks: str | None = None) -> dict[str, object]:
        leave_request = db.get(LeaveRequest, leave_request_id)
        if leave_request is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave request not found")
        if leave_request.status != LeaveRequestStatus.PENDING.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending leave requests can be decided")

        employee = db.execute(
            select(Employee).options(joinedload(Employee.user)).where(Employee.id == leave_request.employee_id)
        ).scalar_one()
        leave_type = db.get(LeaveType, leave_request.leave_type_id)

        normalized_decision = decision.lower()
        if normalized_decision not in {LeaveRequestStatus.APPROVED.value, LeaveRequestStatus.REJECTED.value}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Decision must be approved or rejected")

        normalized_remarks = (remarks or "").strip() or None
        acted_at = datetime.now(UTC)

        if normalized_decision == LeaveRequestStatus.REJECTED.value and not normalized_remarks:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rejection reason is required")

        if normalized_decision == LeaveRequestStatus.APPROVED.value:
            balances = LeaveService._ensure_balances(db, employee_id=str(employee.id), year=leave_request.start_date.year)
            target_balance = next((item for item in balances if str(item.leave_type_id) == str(leave_request.leave_type_id)), None)
            if target_balance is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave balance is not available")
            if Decimal(target_balance.remaining_days) < Decimal(leave_request.total_days):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient leave balance for approval")

            target_balance.used_days = Decimal(target_balance.used_days) + Decimal(leave_request.total_days)
            target_balance.remaining_days = Decimal(target_balance.remaining_days) - Decimal(leave_request.total_days)
            leave_request.status = LeaveRequestStatus.APPROVED.value
            leave_request.approved_at = acted_at
            leave_request.rejected_at = None
            leave_request.remarks = normalized_remarks
            for leave_day in LeaveService._date_range(leave_request.start_date, leave_request.end_date):
                logs = db.execute(
                    select(AttendanceLog)
                    .where(
                        AttendanceLog.employee_id == leave_request.employee_id,
                        AttendanceLog.attendance_date == leave_day,
                    )
                    .order_by(AttendanceLog.updated_at.desc(), AttendanceLog.created_at.desc())
                ).scalars().all()
                attendance_log = logs[0] if logs else None
                if attendance_log is None:
                    attendance_log = AttendanceLog(
                        employee_id=leave_request.employee_id,
                        attendance_date=leave_day,
                        status=AttendanceStatus.LEAVE.value,
                        work_minutes=0,
                        work_seconds=0,
                        is_late=False,
                        source="leave",
                        corrected_by_user_id=auth.user.id,
                        corrected_at=acted_at,
                    )
                    db.add(attendance_log)
                else:
                    attendance_log.status = AttendanceStatus.LEAVE.value
                    attendance_log.check_in_at = None
                    attendance_log.check_out_at = None
                    attendance_log.work_minutes = 0
                    attendance_log.work_seconds = 0
                    attendance_log.is_late = False
                    attendance_log.source = "leave"
                    attendance_log.corrected_by_user_id = auth.user.id
                    attendance_log.corrected_at = acted_at

                for duplicate_log in logs[1:]:
                    db.delete(duplicate_log)

                summary = db.execute(
                    select(AttendanceDailySummary).where(
                        AttendanceDailySummary.employee_id == leave_request.employee_id,
                        AttendanceDailySummary.summary_date == leave_day,
                    )
                ).scalar_one_or_none()
                if summary is None:
                    summary = AttendanceDailySummary(
                        employee_id=leave_request.employee_id,
                        summary_date=leave_day,
                        status=AttendanceStatus.LEAVE.value,
                        work_minutes=0,
                        leave_request_id=leave_request.id,
                    )
                    db.add(summary)
                else:
                    summary.status = AttendanceStatus.LEAVE.value
                    summary.leave_request_id = leave_request.id
                    summary.work_minutes = 0
        else:
            leave_request.status = LeaveRequestStatus.REJECTED.value
            leave_request.rejected_at = acted_at
            leave_request.approved_at = None
            leave_request.remarks = normalized_remarks

        db.add(
            LeaveApproval(
                leave_request_id=leave_request.id,
                approver_user_id=auth.user.id,
                decision=normalized_decision,
                remarks=normalized_remarks,
                acted_at=acted_at,
            )
        )

        NotificationService.create_user_notification(
            db,
            user_id=employee.user_id,
            title=f"Leave request {normalized_decision}",
            message=f"Your {leave_type.name} request from {leave_request.start_date} to {leave_request.end_date} was {normalized_decision}.",
            notification_type=f"leave_{normalized_decision}",
            metadata_json={"leave_request_id": str(leave_request.id)},
            employee_id=employee.id,
            related_id=leave_request.id,
            target_url="/leave",
        )
        db.commit()
        email_sent, email_error = LeaveService._send_leave_decision_email(
            employee=employee,
            leave_type=leave_type,
            leave_request=leave_request,
            decision=normalized_decision,
            remarks=normalized_remarks,
        )
        response_message = f"Leave request {normalized_decision} successfully"
        if not email_sent:
            response_message = f"{response_message}, but email notification could not be sent."
        return {
            "message": response_message,
            "leave_request_id": leave_request.id,
            "email_sent": email_sent,
            "email_error": email_error,
        }
