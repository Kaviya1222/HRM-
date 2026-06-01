from __future__ import annotations

from contextlib import suppress

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


def ensure_database_exists(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql") or not url.database:
        return

    database_name = url.database.replace("`", "``")
    server_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        query=url.query,
    )
    server_engine = create_engine(server_url, future=True, pool_pre_ping=True)

    with server_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )

    server_engine.dispose()


def ensure_attendance_runtime_schema(engine) -> None:
    if not engine.dialect.name.startswith("mysql"):
        return

    with engine.begin() as connection:
        columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM attendance_logs")).mappings()
        }
        if "user_id" not in columns:
            connection.execute(text("ALTER TABLE attendance_logs ADD COLUMN user_id CHAR(32) NULL AFTER employee_id"))
            connection.execute(text("CREATE INDEX ix_attendance_logs_user_id ON attendance_logs (user_id)"))
            connection.execute(text("CREATE INDEX ix_attendance_logs_user_date ON attendance_logs (user_id, attendance_date)"))
        if "work_seconds" not in columns:
            connection.execute(text("ALTER TABLE attendance_logs ADD COLUMN work_seconds INT NOT NULL DEFAULT 0 AFTER work_minutes"))

        summary_columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM attendance_daily_summary")).mappings()
        }
        if "work_seconds" not in summary_columns:
            connection.execute(text("ALTER TABLE attendance_daily_summary ADD COLUMN work_seconds INT NOT NULL DEFAULT 0 AFTER work_minutes"))

        employee_column = connection.execute(text("SHOW COLUMNS FROM attendance_logs LIKE 'employee_id'")).mappings().first()
        if employee_column and employee_column.get("Null") == "NO":
            connection.execute(text("ALTER TABLE attendance_logs MODIFY employee_id CHAR(32) NULL"))

        indexes = {
            row["Key_name"]
            for row in connection.execute(text("SHOW INDEX FROM attendance_logs")).mappings()
        }
        if "uq_attendance_logs_employee_date" in indexes:
            with suppress(Exception):
                connection.execute(text("ALTER TABLE attendance_logs DROP INDEX uq_attendance_logs_employee_date"))
        if "uq_attendance_logs_user_date" in indexes:
            with suppress(Exception):
                connection.execute(text("ALTER TABLE attendance_logs DROP INDEX uq_attendance_logs_user_date"))


def ensure_leave_runtime_schema(engine) -> None:
    if not engine.dialect.name.startswith("mysql"):
        return

    with engine.begin() as connection:
        columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM leave_requests")).mappings()
        }
        if "reason" not in columns:
            connection.execute(text("ALTER TABLE leave_requests ADD COLUMN reason TEXT NULL AFTER total_days"))
        if "approved_at" not in columns:
            connection.execute(text("ALTER TABLE leave_requests ADD COLUMN approved_at DATETIME NULL AFTER requested_at"))
        if "rejected_at" not in columns:
            connection.execute(text("ALTER TABLE leave_requests ADD COLUMN rejected_at DATETIME NULL AFTER approved_at"))
        if "remarks" not in columns:
            connection.execute(text("ALTER TABLE leave_requests ADD COLUMN remarks TEXT NULL AFTER rejected_at"))


def ensure_notification_runtime_schema(engine) -> None:
    if not engine.dialect.name.startswith("mysql"):
        return

    with engine.begin() as connection:
        columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM notifications")).mappings()
        }
        if "employee_id" not in columns:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN employee_id CHAR(32) NULL AFTER user_id"))
            connection.execute(text("CREATE INDEX ix_notifications_employee_id ON notifications (employee_id)"))
        if "event_id" not in columns:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN event_id CHAR(32) NULL AFTER employee_id"))
            connection.execute(text("CREATE INDEX ix_notifications_event_id ON notifications (event_id)"))
        if "related_id" not in columns:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN related_id VARCHAR(80) NULL AFTER event_id"))
            connection.execute(text("CREATE INDEX ix_notifications_related_id ON notifications (related_id)"))
        if "target_url" not in columns:
            connection.execute(text("ALTER TABLE notifications ADD COLUMN target_url VARCHAR(180) NULL AFTER related_id"))


def ensure_payroll_runtime_schema(engine) -> None:
    if not engine.dialect.name.startswith("mysql"):
        return

    with engine.begin() as connection:
        columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM payslips")).mappings()
        }
        additions = [
            ("monthly_salary", "ALTER TABLE payslips ADD COLUMN monthly_salary DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER employee_id"),
            ("total_days", "ALTER TABLE payslips ADD COLUMN total_days INT NOT NULL DEFAULT 30 AFTER monthly_salary"),
            ("worked_days", "ALTER TABLE payslips ADD COLUMN worked_days DECIMAL(8, 2) NOT NULL DEFAULT 0 AFTER total_days"),
            ("per_day_salary", "ALTER TABLE payslips ADD COLUMN per_day_salary DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER worked_days"),
            ("basic", "ALTER TABLE payslips ADD COLUMN basic DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER per_day_salary"),
            ("hra", "ALTER TABLE payslips ADD COLUMN hra DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER basic"),
            ("special_allowance", "ALTER TABLE payslips ADD COLUMN special_allowance DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER hra"),
            ("transport", "ALTER TABLE payslips ADD COLUMN transport DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER special_allowance"),
            ("medical", "ALTER TABLE payslips ADD COLUMN medical DECIMAL(12, 2) NOT NULL DEFAULT 0 AFTER transport"),
        ]
        for column_name, ddl in additions:
            if column_name not in columns:
                connection.execute(text(ddl))

        transaction_columns = {
            row["Field"]
            for row in connection.execute(text("SHOW COLUMNS FROM payroll_transactions")).mappings()
        }
        if "employee_name" not in transaction_columns:
            connection.execute(text("ALTER TABLE payroll_transactions ADD COLUMN employee_name VARCHAR(160) NULL AFTER employee_id"))

        tables = {
            row[0]
            for row in connection.execute(text("SHOW TABLES")).all()
        }
        if "salary_profiles" not in tables:
            connection.execute(
                text(
                    "CREATE TABLE salary_profiles ("
                    "id CHAR(32) NOT NULL, "
                    "employee_id CHAR(32) NOT NULL, "
                    "date_joined DATE NULL, "
                    "department VARCHAR(120) NULL, "
                    "sub_department VARCHAR(120) NULL, "
                    "designation VARCHAR(120) NULL, "
                    "payment_mode VARCHAR(80) NULL, "
                    "bank VARCHAR(120) NULL, "
                    "bank_ifsc VARCHAR(40) NULL, "
                    "bank_account_number VARCHAR(80) NULL, "
                    "uan VARCHAR(80) NULL, "
                    "pf_number VARCHAR(80) NULL, "
                    "pan_number VARCHAR(40) NULL, "
                    "actual_payable_days DECIMAL(8, 2) NULL, "
                    "total_working_days DECIMAL(8, 2) NULL, "
                    "loss_of_pay DECIMAL(8, 2) NULL, "
                    "present_days DECIMAL(8, 2) NULL, "
                    "salary_amount DECIMAL(12, 2) NULL, "
                    "salary_transaction_id CHAR(32) NULL, "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                    "PRIMARY KEY (id), "
                    "CONSTRAINT uq_salary_profiles_employee UNIQUE (employee_id), "
                    "CONSTRAINT fk_salary_profiles_employee_id_employees FOREIGN KEY (employee_id) REFERENCES employees (id) ON DELETE CASCADE"
                    ")"
                )
            )
            connection.execute(text("CREATE INDEX ix_salary_profiles_employee_id ON salary_profiles (employee_id)"))
            connection.execute(text("CREATE INDEX ix_salary_profiles_salary_transaction_id ON salary_profiles (salary_transaction_id)"))
        else:
            salary_profile_columns = {
                row["Field"]
                for row in connection.execute(text("SHOW COLUMNS FROM salary_profiles")).mappings()
            }
            profile_additions = [
                ("total_working_days", "ALTER TABLE salary_profiles ADD COLUMN total_working_days DECIMAL(8, 2) NULL AFTER pan_number"),
                ("actual_payable_days", "ALTER TABLE salary_profiles ADD COLUMN actual_payable_days DECIMAL(8, 2) NULL AFTER pan_number"),
                ("loss_of_pay", "ALTER TABLE salary_profiles ADD COLUMN loss_of_pay DECIMAL(8, 2) NULL AFTER total_working_days"),
                ("present_days", "ALTER TABLE salary_profiles ADD COLUMN present_days DECIMAL(8, 2) NULL AFTER loss_of_pay"),
                ("salary_amount", "ALTER TABLE salary_profiles ADD COLUMN salary_amount DECIMAL(12, 2) NULL AFTER present_days"),
                ("salary_transaction_id", "ALTER TABLE salary_profiles ADD COLUMN salary_transaction_id CHAR(32) NULL AFTER salary_amount"),
            ]
            for column_name, ddl in profile_additions:
                if column_name not in salary_profile_columns:
                    connection.execute(text(ddl))
            indexes = {
                row["Key_name"]
                for row in connection.execute(text("SHOW INDEX FROM salary_profiles")).mappings()
            }
            if "ix_salary_profiles_salary_transaction_id" not in indexes:
                connection.execute(text("CREATE INDEX ix_salary_profiles_salary_transaction_id ON salary_profiles (salary_transaction_id)"))


def ensure_tracker_runtime_schema(engine) -> None:
    if not engine.dialect.name.startswith("mysql"):
        return

    with engine.begin() as connection:
        device_columns = {
            row["Field"]: row
            for row in connection.execute(text("SHOW COLUMNS FROM devices")).mappings()
        }
        if "user_id" not in device_columns:
            connection.execute(text("ALTER TABLE devices ADD COLUMN user_id CHAR(32) NULL AFTER employee_id"))
            connection.execute(text("CREATE INDEX ix_devices_user_id ON devices (user_id)"))
        employee_column = device_columns.get("employee_id")
        if employee_column and employee_column.get("Null") == "NO":
            connection.execute(text("ALTER TABLE devices MODIFY employee_id CHAR(32) NULL"))

        columns = {
            row["Field"]: row
            for row in connection.execute(text("SHOW COLUMNS FROM tracker_sessions")).mappings()
        }
        if "last_active_at" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN last_active_at DATETIME NULL AFTER logout_time"))
        if "last_heartbeat" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN last_heartbeat DATETIME NULL AFTER logout_time"))
        if "user_id" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN user_id CHAR(32) NULL AFTER employee_id"))
            connection.execute(text("CREATE INDEX ix_tracker_sessions_user_id ON tracker_sessions (user_id)"))
        if "session_token" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN session_token VARCHAR(128) NULL AFTER last_active_at"))
            connection.execute(text("CREATE UNIQUE INDEX ix_tracker_sessions_session_token ON tracker_sessions (session_token)"))
        if "device_info" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN device_info JSON NULL AFTER session_token"))
        if "ip_address" not in columns:
            connection.execute(text("ALTER TABLE tracker_sessions ADD COLUMN ip_address VARCHAR(64) NULL AFTER device_info"))
        session_employee_column = columns.get("employee_id")
        if session_employee_column and session_employee_column.get("Null") == "NO":
            connection.execute(text("ALTER TABLE tracker_sessions MODIFY employee_id CHAR(32) NULL"))

        indexes = {
            row["Key_name"]
            for row in connection.execute(text("SHOW INDEX FROM tracker_sessions")).mappings()
        }
        if "ix_tracker_sessions_employee_online" not in indexes:
            connection.execute(text("CREATE INDEX ix_tracker_sessions_employee_online ON tracker_sessions (employee_id, is_online, last_active_at)"))
        if "ix_tracker_sessions_status_heartbeat" not in indexes:
            connection.execute(text("CREATE INDEX ix_tracker_sessions_status_heartbeat ON tracker_sessions (status, is_online, last_active_at)"))

        heartbeat_columns = {
            row["Field"]: row
            for row in connection.execute(text("SHOW COLUMNS FROM tracker_heartbeats")).mappings()
        }
        if "user_id" not in heartbeat_columns:
            connection.execute(text("ALTER TABLE tracker_heartbeats ADD COLUMN user_id CHAR(32) NULL AFTER employee_id"))
            connection.execute(text("CREATE INDEX ix_tracker_heartbeats_user_id ON tracker_heartbeats (user_id)"))
        heartbeat_employee_column = heartbeat_columns.get("employee_id")
        if heartbeat_employee_column and heartbeat_employee_column.get("Null") == "NO":
            connection.execute(text("ALTER TABLE tracker_heartbeats MODIFY employee_id CHAR(32) NULL"))
