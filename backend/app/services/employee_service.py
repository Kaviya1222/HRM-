from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.api.deps import AuthContext
from app.core.constants import RoleCode
from app.core.security import get_password_hash
from app.models.auth import Role, User
from app.models.employee import Department, Designation, Employee, ReportingManager
from app.models.enums import EmployeeStatus, UserStatus
from app.models.utility import AuditLog


class EmployeeService:
    @staticmethod
    def _db_id(value: UUID | str | None) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _employee_query():
        return (
            select(Employee)
            .options(
                joinedload(Employee.user).joinedload(User.role),
                joinedload(Employee.department),
                joinedload(Employee.designation),
                joinedload(Employee.manager).joinedload(Employee.user).joinedload(User.role),
            )
            .where(Employee.is_deleted.is_(False))
        )

    @staticmethod
    def _serialize_role(role: Role | None) -> dict[str, object] | None:
        if role is None:
            return None
        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "hierarchy_rank": role.hierarchy_rank,
        }

    @staticmethod
    def _serialize_department(department: Department | None) -> dict[str, object] | None:
        if department is None:
            return None
        return {"id": department.id, "name": department.name, "code": department.code}

    @staticmethod
    def _serialize_designation(designation: Designation | None) -> dict[str, object] | None:
        if designation is None:
            return None
        return {"id": designation.id, "name": designation.name, "code": designation.code}

    @staticmethod
    def _serialize_manager(manager: Employee | None) -> dict[str, object] | None:
        if manager is None:
            return None
        manager_user = manager.user
        return {
            "id": manager.id,
            "employee_code": manager.employee_code,
            "full_name": manager_user.full_name if manager_user else manager.employee_code,
            "role_name": manager_user.role.name if manager_user and manager_user.role else None,
        }

    @staticmethod
    def serialize_employee(employee: Employee) -> dict[str, object]:
        user = employee.user
        return {
            "id": employee.id,
            "user_id": user.id if user else None,
            "employee_code": employee.employee_code,
            "email": user.email if user else None,
            "first_name": user.first_name if user else None,
            "last_name": user.last_name if user else None,
            "full_name": user.full_name if user else employee.employee_code,
            "role": EmployeeService._serialize_role(user.role if user else None),
            "department": EmployeeService._serialize_department(employee.department),
            "designation": EmployeeService._serialize_designation(employee.designation),
            "manager": EmployeeService._serialize_manager(employee.manager),
            "joining_date": employee.joining_date,
            "date_of_birth": employee.date_of_birth,
            "phone_number": employee.phone_number,
            "address": employee.address,
            "base_salary": employee.base_salary,
            "is_billable": employee.is_billable,
            "status": employee.status,
            "is_active": bool(user.is_active) if user else employee.status == EmployeeStatus.ACTIVE.value,
            "created_at": employee.created_at,
            "updated_at": employee.updated_at,
        }

    @staticmethod
    def _get_employee_or_404(db: Session, employee_id: UUID | str) -> Employee:
        employee = db.execute(EmployeeService._employee_query().where(Employee.id == EmployeeService._db_id(employee_id))).scalars().unique().first()
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        return employee

    @staticmethod
    def _get_role_or_404(db: Session, role_id: UUID | str) -> Role:
        role = db.get(Role, EmployeeService._db_id(role_id))
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role

    @staticmethod
    def _get_department_or_none(db: Session, department_id: UUID | str | None) -> Department | None:
        if department_id is None:
            return None
        department = db.get(Department, EmployeeService._db_id(department_id))
        if department is None or department.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
        return department

    @staticmethod
    def _get_designation_or_none(db: Session, designation_id: UUID | str | None) -> Designation | None:
        if designation_id is None:
            return None
        designation = db.get(Designation, EmployeeService._db_id(designation_id))
        if designation is None or designation.is_deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Designation not found")
        return designation

    @staticmethod
    def _get_manager_or_none(db: Session, manager_id: UUID | str | None) -> Employee | None:
        if manager_id is None:
            return None
        manager = EmployeeService._get_employee_or_404(db, manager_id)
        if manager.status != EmployeeStatus.ACTIVE.value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reporting manager must be active")
        return manager

    @staticmethod
    def _ensure_unique_email(db: Session, email: str, exclude_user_id: UUID | str | None = None) -> None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != EmployeeService._db_id(exclude_user_id))
        if db.execute(stmt).scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists")

    @staticmethod
    def _ensure_unique_employee_code(db: Session, employee_code: str, exclude_employee_id: UUID | str | None = None) -> None:
        stmt = select(Employee).where(func.lower(Employee.employee_code) == employee_code.lower(), Employee.is_deleted.is_(False))
        if exclude_employee_id is not None:
            stmt = stmt.where(Employee.id != EmployeeService._db_id(exclude_employee_id))
        if db.execute(stmt).scalar_one_or_none() is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee code already exists")

    @staticmethod
    def _ensure_actor_can_assign_role(auth: AuthContext, role: Role) -> None:
        actor_role = auth.user.role
        if actor_role.code == RoleCode.SUPER_ADMIN.value:
            return
        if role.code == RoleCode.SUPER_ADMIN.value or role.hierarchy_rank <= actor_role.hierarchy_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot assign a role at your own level or higher in the hierarchy",
            )

    @staticmethod
    def _ensure_actor_can_manage_target(auth: AuthContext, target_user: User | None) -> None:
        if target_user is None or auth.user.role.code == RoleCode.SUPER_ADMIN.value:
            return
        if target_user.role.hierarchy_rank <= auth.user.role.hierarchy_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You cannot manage a user at your own level or higher in the hierarchy",
            )

    @staticmethod
    def _replace_reporting_manager(
        db: Session,
        *,
        employee: Employee,
        manager: Employee | None,
        start_date: date | None = None,
    ) -> None:
        today = start_date or date.today()
        active_rows = db.execute(
            select(ReportingManager).where(
                ReportingManager.employee_id == employee.id,
                ReportingManager.end_date.is_(None),
                ReportingManager.is_primary.is_(True),
            )
        ).scalars().all()

        for row in active_rows:
            row.end_date = today

        employee.manager_id = manager.id if manager else None
        if manager is not None:
            db.add(
                ReportingManager(
                    employee_id=employee.id,
                    manager_id=manager.id,
                    start_date=today,
                    is_primary=True,
                )
            )

    @staticmethod
    def _add_audit_log(
        db: Session,
        *,
        actor_user_id: UUID | str | None,
        entity_type: str,
        entity_id: UUID | str,
        action: str,
        before_data: dict[str, object] | None = None,
        after_data: dict[str, object] | None = None,
    ) -> None:
        db.add(
            AuditLog(
                actor_user_id=actor_user_id,
                entity_type=entity_type,
                entity_id=str(entity_id),
                action=action,
                before_data=jsonable_encoder(before_data) if before_data is not None else None,
                after_data=jsonable_encoder(after_data) if after_data is not None else None,
            )
        )

    @staticmethod
    def list_employees(
        db: Session,
        *,
        search: str | None = None,
        status: str | None = None,
        department_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> dict[str, object]:
        stmt = EmployeeService._employee_query().join(User, Employee.user_id == User.id, isouter=True)

        if search:
            search_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Employee.employee_code).like(search_term),
                    func.lower(User.first_name).like(search_term),
                    func.lower(User.last_name).like(search_term),
                    func.lower(User.email).like(search_term),
                )
            )

        if status:
            stmt = stmt.where(Employee.status == status)
        if department_id:
            stmt = stmt.where(Employee.department_id == department_id)
        if is_active is not None:
            stmt = stmt.where(User.is_active.is_(is_active))

        employees = db.execute(stmt.order_by(Employee.created_at.desc())).scalars().unique().all()
        items = [EmployeeService.serialize_employee(employee) for employee in employees]
        return {"items": items, "total": len(items)}

    @staticmethod
    def get_employee_detail(db: Session, employee_id: UUID | str) -> dict[str, object]:
        employee = EmployeeService._get_employee_or_404(db, employee_id)
        return EmployeeService.serialize_employee(employee)

    @staticmethod
    def get_employee_meta(db: Session, auth: AuthContext) -> dict[str, object]:
        roles = db.execute(select(Role).order_by(Role.hierarchy_rank.asc())).scalars().all()

        departments = db.execute(
            select(Department).where(Department.is_deleted.is_(False)).order_by(Department.name.asc())
        ).scalars().all()
        designations = db.execute(
            select(Designation).where(Designation.is_deleted.is_(False)).order_by(Designation.name.asc())
        ).scalars().all()
        managers = db.execute(
            EmployeeService._employee_query().join(User, Employee.user_id == User.id).where(
                Employee.status == EmployeeStatus.ACTIVE.value,
                User.is_active.is_(True),
            )
        ).scalars().unique().all()

        return {
            "roles": [EmployeeService._serialize_role(role) for role in roles],
            "departments": [EmployeeService._serialize_department(item) for item in departments],
            "designations": [EmployeeService._serialize_designation(item) for item in designations],
            "managers": [EmployeeService._serialize_manager(item) for item in managers],
        }

    @staticmethod
    def create_employee(db: Session, auth: AuthContext, payload: dict[str, object]) -> dict[str, object]:
        email = str(payload["email"]).strip().lower()
        employee_code = str(payload["employee_code"]).strip()

        EmployeeService._ensure_unique_email(db, email)
        EmployeeService._ensure_unique_employee_code(db, employee_code)

        role = EmployeeService._get_role_or_404(db, payload["role_id"])
        EmployeeService._ensure_actor_can_assign_role(auth, role)

        department = EmployeeService._get_department_or_none(db, payload.get("department_id"))
        designation = EmployeeService._get_designation_or_none(db, payload.get("designation_id"))
        manager = EmployeeService._get_manager_or_none(db, payload.get("manager_id"))

        try:
            user = User(
                email=email,
                password_hash=get_password_hash(str(payload["password"])),
                first_name=str(payload["first_name"]).strip(),
                last_name=str(payload["last_name"]).strip(),
                role_id=role.id,
                is_active=True,
                status=UserStatus.ACTIVE.value,
            )
            db.add(user)
            db.flush()

            employee = Employee(
                user_id=user.id,
                employee_code=employee_code,
                department_id=department.id if department else None,
                designation_id=designation.id if designation else None,
                manager_id=manager.id if manager else None,
                joining_date=payload.get("joining_date"),
                date_of_birth=payload.get("date_of_birth"),
                phone_number=payload.get("phone_number"),
                address=payload.get("address"),
                base_salary=payload.get("base_salary"),
                is_billable=bool(payload.get("is_billable", True)),
                status=EmployeeStatus.ACTIVE.value,
            )
            db.add(employee)
            db.flush()

            if manager is not None:
                EmployeeService._replace_reporting_manager(
                    db,
                    employee=employee,
                    manager=manager,
                    start_date=payload.get("joining_date") or date.today(),
                )

            db.flush()

            # Initialize leave balances so the employee is available in Leave workflows immediately.
            from app.services.leave_service import LeaveService
            LeaveService.initialize_leave_balances_for_employee(db, str(employee.id))

            created_payload = EmployeeService.serialize_employee(EmployeeService._get_employee_or_404(db, employee.id))
            EmployeeService._add_audit_log(
                db,
                actor_user_id=auth.user.id,
                entity_type="employee",
                entity_id=employee.id,
                action="employee.create",
                after_data=created_payload,
            )
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Employee could not be saved because one or more selected values are invalid or already used.",
            ) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Employee could not be saved due to a database error.",
            ) from exc

        return EmployeeService.get_employee_detail(db, employee.id)

    @staticmethod
    def update_employee(db: Session, auth: AuthContext, employee_id: UUID | str, payload: dict[str, object]) -> dict[str, object]:
        employee = EmployeeService._get_employee_or_404(db, employee_id)
        if employee.user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee is not linked to a user account")

        EmployeeService._ensure_actor_can_manage_target(auth, employee.user)

        email = str(payload["email"]).strip().lower()
        employee_code = str(payload["employee_code"]).strip()

        EmployeeService._ensure_unique_email(db, email, exclude_user_id=employee.user.id)
        EmployeeService._ensure_unique_employee_code(db, employee_code, exclude_employee_id=employee.id)

        role = EmployeeService._get_role_or_404(db, payload["role_id"])
        EmployeeService._ensure_actor_can_assign_role(auth, role)

        department = EmployeeService._get_department_or_none(db, payload.get("department_id"))
        designation = EmployeeService._get_designation_or_none(db, payload.get("designation_id"))
        manager = EmployeeService._get_manager_or_none(db, payload.get("manager_id"))

        if manager is not None and manager.id == employee.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An employee cannot report to themselves")

        before_payload = EmployeeService.serialize_employee(employee)

        employee.user.email = email
        employee.user.first_name = str(payload["first_name"]).strip()
        employee.user.last_name = str(payload["last_name"]).strip()
        employee.user.role_id = role.id

        password = payload.get("password")
        if password:
            employee.user.password_hash = get_password_hash(str(password))

        employee.employee_code = employee_code
        employee.department_id = department.id if department else None
        employee.designation_id = designation.id if designation else None
        employee.joining_date = payload.get("joining_date")
        employee.date_of_birth = payload.get("date_of_birth")
        employee.phone_number = payload.get("phone_number")
        employee.address = payload.get("address")
        employee.base_salary = payload.get("base_salary")
        employee.is_billable = bool(payload.get("is_billable", True))

        if manager is None and employee.manager_id is not None:
            EmployeeService._replace_reporting_manager(db, employee=employee, manager=None)
        elif manager is not None and manager.id != employee.manager_id:
            EmployeeService._replace_reporting_manager(db, employee=employee, manager=manager)

        db.flush()
        updated_payload = EmployeeService.serialize_employee(EmployeeService._get_employee_or_404(db, employee.id))
        EmployeeService._add_audit_log(
            db,
            actor_user_id=auth.user.id,
            entity_type="employee",
            entity_id=employee.id,
            action="employee.update",
            before_data=before_payload,
            after_data=updated_payload,
        )
        db.commit()
        return EmployeeService.get_employee_detail(db, employee.id)

    @staticmethod
    def update_employee_status(
        db: Session,
        auth: AuthContext,
        *,
        employee_id: UUID | str,
        is_active: bool,
    ) -> dict[str, object]:
        employee = EmployeeService._get_employee_or_404(db, employee_id)
        if employee.user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee is not linked to a user account")

        EmployeeService._ensure_actor_can_manage_target(auth, employee.user)
        if employee.user_id == auth.user.id and not is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account")

        before_payload = EmployeeService.serialize_employee(employee)
        employee.user.is_active = is_active
        employee.user.status = UserStatus.ACTIVE.value if is_active else UserStatus.INACTIVE.value
        employee.status = EmployeeStatus.ACTIVE.value if is_active else EmployeeStatus.INACTIVE.value

        db.flush()
        after_payload = EmployeeService.serialize_employee(EmployeeService._get_employee_or_404(db, employee.id))
        EmployeeService._add_audit_log(
            db,
            actor_user_id=auth.user.id,
            entity_type="employee",
            entity_id=employee.id,
            action="employee.status_update",
            before_data=before_payload,
            after_data=after_payload,
        )
        db.commit()
        return after_payload

    @staticmethod
    def delete_employee(db: Session, auth: AuthContext, employee_id: UUID | str) -> dict[str, object]:
        employee = EmployeeService._get_employee_or_404(db, employee_id)
        if employee.user is not None:
            EmployeeService._ensure_actor_can_manage_target(auth, employee.user)
            if employee.user_id == auth.user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own employee record")

        before_payload = EmployeeService.serialize_employee(employee)
        employee.is_deleted = True
        employee.deleted_at = datetime.now(UTC)
        employee.status = EmployeeStatus.INACTIVE.value
        if employee.user is not None:
            employee.user.is_active = False
            employee.user.status = UserStatus.INACTIVE.value

        db.flush()
        EmployeeService._add_audit_log(
            db,
            actor_user_id=auth.user.id,
            entity_type="employee",
            entity_id=employee.id,
            action="employee.delete",
            before_data=before_payload,
            after_data={"is_deleted": True},
        )
        db.commit()
        return {"message": "Employee deleted successfully"}

    @staticmethod
    def assign_manager(
        db: Session,
        auth: AuthContext,
        *,
        employee_id: UUID | str,
        manager_id: UUID | str | None,
        start_date: date | None = None,
    ) -> dict[str, object]:
        employee = EmployeeService._get_employee_or_404(db, employee_id)
        if employee.user is not None:
            EmployeeService._ensure_actor_can_manage_target(auth, employee.user)

        manager = EmployeeService._get_manager_or_none(db, manager_id)
        if manager is not None and manager.id == employee.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An employee cannot report to themselves")

        before_payload = EmployeeService.serialize_employee(employee)
        EmployeeService._replace_reporting_manager(db, employee=employee, manager=manager, start_date=start_date)
        db.flush()
        after_payload = EmployeeService.serialize_employee(EmployeeService._get_employee_or_404(db, employee.id))
        EmployeeService._add_audit_log(
            db,
            actor_user_id=auth.user.id,
            entity_type="employee",
            entity_id=employee.id,
            action="employee.manager_update",
            before_data=before_payload,
            after_data=after_payload,
        )
        db.commit()
        return after_payload
