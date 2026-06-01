# HRM Project Codebase Analysis

## Executive Summary
The HRM project is a full-stack application with a FastAPI backend and React Vite frontend. It has well-defined models for Employee, Attendance, and Leave management, with comprehensive API endpoints and working frontend components. The project includes a tracker client for monitoring employee activities.

---

## 1. BACKEND MODELS

### 1.1 Employee Model Structure
**File**: `backend/app/models/employee.py`

#### Department Model
- **id** (UUID, PK)
- **name** (String, unique)codex
- **code** (String, unique)
- **description** (Text, nullable)
- **Relationships**: One-to-Many with Employee

#### Designation Model
- **id** (UUID, PK)
- **name** (String, unique)
- **code** (String, unique)
- **description** (Text, nullable)
- **Relationships**: One-to-Many with Employee

#### Employee Model (Main)
- **id** (UUID, PK) - inherited from UUIDPrimaryKeyMixin
- **user_id** (FK → users.id, nullable, unique) - Links to User account
- **employee_code** (String, unique, indexed)
- **department_id** (FK → departments.id, nullable)
- **designation_id** (FK → designations.id, nullable)
- **manager_id** (FK → employees.id, self-referential, nullable)
- **joining_date** (Date, nullable)
- **date_of_birth** (Date, nullable)
- **phone_number** (String, max 30)
- **address** (Text, nullable)
- **status** (String) - Values: "active", "inactive" (default: "active")
- **base_salary** (Decimal 12,2, nullable)
- **is_billable** (Boolean, default: True)
- **created_at** (DateTime) - inherited from TimestampMixin
- **updated_at** (DateTime) - inherited from TimestampMixin
- **is_deleted** (Boolean) - inherited from SoftDeleteMixin

**Relationships**:
- `user`: One-to-One with User
- `department`: Many-to-One with Department
- `designation`: Many-to-One with Designation
- `manager`: Self-referential (parent Employee)
- `direct_reports`: Self-referential (child Employees)

#### ReportingManager Model
- **id** (UUID, PK)
- **employee_id** (FK → employees.id, CASCADE)
- **manager_id** (FK → employees.id, CASCADE)
- **start_date** (Date)
- **end_date** (Date, nullable)
- **is_primary** (Boolean, default: True)
- **Unique constraint**: (employee_id, manager_id, start_date)

---

### 1.2 Attendance Model Structure
**File**: `backend/app/models/attendance.py`

#### AttendanceRule Model
- **id** (UUID, PK)
- **name** (String)
- **late_mark_after_minutes** (Integer, default: 15)
- **half_day_min_minutes** (Integer, default: 240)
- **full_day_min_minutes** (Integer, default: 480)
- **effective_from** (Date)
- **is_active** (Boolean, default: True)

#### AttendanceLog Model (Main)
- **id** (UUID, PK)
- **employee_id** (FK → employees.id, CASCADE, indexed)
- **attendance_date** (Date, indexed)
- **check_in_at** (DateTime with timezone, nullable)
- **check_out_at** (DateTime with timezone, nullable)
- **work_minutes** (Integer, default: 0)
- **status** (String) - Values: "present", "absent", "half_day", "leave" (default: "absent")
- **is_late** (Boolean, default: False)
- **source** (String, default: "web")
- **corrected_by_user_id** (FK → users.id, nullable)
- **corrected_at** (DateTime with timezone, nullable)
- **Composite Index**: (employee_id, attendance_date)

#### AttendanceDailySummary Model
- **id** (UUID, PK)
- **employee_id** (FK → employees.id, CASCADE, indexed)
- **summary_date** (Date, indexed)
- **status** (String)
- **work_minutes** (Integer, default: 0)
- **idle_minutes** (Integer, default: 0)
- **leave_request_id** (FK → leave_requests.id, nullable)
- **Composite Index**: (employee_id, summary_date)

#### AttendanceCorrection Model
- **id** (UUID, PK)
- **attendance_log_id** (FK → attendance_logs.id, CASCADE, indexed)
- **requested_by_user_id** (FK → users.id, indexed)
- **approved_by_user_id** (FK → users.id, nullable, indexed)
- **reason** (Text)
- **old_data** (JSON, nullable)
- **new_data** (JSON, nullable)
- **status** (String, default: "pending")

#### AttendanceAuditLog Model
- **id** (UUID, PK)
- **attendance_log_id** (FK → attendance_logs.id, CASCADE, indexed)
- **changed_by_user_id** (FK → users.id, nullable, indexed)
- **action** (String)
- **before_data** (JSON, nullable)
- **after_data** (JSON, nullable)

**✓ KEY FINDING**: Attendance has ForeignKey to Employee (employee_id) ✓

---

### 1.3 Leave Model Structure
**File**: `backend/app/models/leave.py`

#### LeaveType Model
- **id** (UUID, PK)
- **name** (String, unique)
- **code** (String, unique)
- **annual_allowance** (Decimal 8,2, default: 0)
- **description** (Text, nullable)

#### LeaveRequest Model (Main)
- **id** (UUID, PK)
- **employee_id** (FK → employees.id, CASCADE, indexed)
- **leave_type_id** (FK → leave_types.id, indexed)
- **start_date** (Date)
- **end_date** (Date)
- **total_days** (Decimal 6,2)
- **reason** (Text, nullable)
- **status** (String) - Values: "pending", "approved", "rejected", "cancelled" (default: "pending")
- **requested_at** (DateTime with timezone)
- **Composite Index**: (employee_id, start_date, end_date)

#### LeaveBalance Model
- **id** (UUID, PK)
- **employee_id** (FK → employees.id, CASCADE, indexed)
- **leave_type_id** (FK → leave_types.id, indexed)
- **year** (Integer)
- **opening_balance** (Decimal 8,2, default: 0)
- **used_days** (Decimal 8,2, default: 0)
- **remaining_days** (Decimal 8,2, default: 0)
- **Unique constraint**: (employee_id, leave_type_id, year)

#### LeaveApproval Model
- **id** (UUID, PK)
- **leave_request_id** (FK → leave_requests.id, CASCADE, indexed)
- **approver_user_id** (FK → users.id, indexed)
- **decision** (String)
- **remarks** (Text, nullable)
- **acted_at** (DateTime with timezone)

**✓ KEY FINDING**: Leave has ForeignKey to Employee (employee_id) ✓

---

### 1.4 Related Models

#### User Model (from auth.py)
- **id** (UUID, PK)
- **email** (String, unique, indexed)
- **password_hash** (String)
- **first_name** (String)
- **last_name** (String)
- **role_id** (FK → roles.id)
- **status** (String) - "active", "inactive"
- **is_active** (Boolean)
- **last_login_at** (DateTime, nullable)
- **full_name** (computed property)
- **Relationship**: One-to-One with Employee (via employee_profile)

#### Tracker Models (from tracker.py)
- **Device**: Tracks devices (employee_id FK)
- **TrackerSession**: Tracks work sessions (employee_id FK)
- **TrackerIdleLog**: Tracks idle time
- **TrackerHeartbeat**: Tracks heartbeats

#### Payroll Models (from payroll.py)
- **SalaryStructure**: (employee_id FK, optional)
- **PayrollRun**: Payroll processing
- **Payslip**: Individual payslips (employee_id FK)

---

## 2. BACKEND APIs

### 2.1 API Route Registration
**File**: `backend/app/api/router.py`

```python
API_PREFIX: /api/v1

Routers:
- /auth → Authentication endpoints
- /dashboard → Dashboard data
- /employees → Employee management
- /attendance → Attendance tracking
- /leave → Leave management
- /payroll → Payroll processing
- /reports → Reports
- /notifications → Notifications
- /tracker → Activity tracking
- /search → Search functionality
- /settings → Super Admin Settings
```

---

### 2.2 Employee Endpoints
**File**: `backend/app/api/v1/endpoints/employees.py`

| Method | Endpoint | Permission | Purpose |
|--------|----------|-----------|---------|
| GET | `/employees/meta` | `employees.view` | Get metadata (roles, departments, designations, managers) |
| GET | `/employees` | `employees.view` | List employees with search, status, department filters |
| POST | `/employees` | `employees.create` + `users.create` | Create new employee |
| GET | `/employees/{employee_id}` | `employees.view` | Get employee detail |
| PUT | `/employees/{employee_id}` | `employees.edit` + `users.edit` | Update employee |
| PATCH | `/employees/{employee_id}/status` | `employees.deactivate` + `users.activate/deactivate` | Toggle employee active status |
| PATCH | `/employees/{employee_id}/manager` | `employees.assign_manager` | Assign reporting manager |

**Query Parameters**:
- `search` (optional): Employee search
- `status` (optional): Filter by employee status
- `department_id` (optional): Filter by department
- `is_active` (optional): Filter by active status

---

### 2.3 Attendance Endpoints
**File**: `backend/app/api/v1/endpoints/attendance.py`

| Method | Endpoint | Permission | Purpose |
|--------|----------|-----------|---------|
| GET | `/attendance/meta` | `attendance.view.*` | Get metadata |
| GET | `/attendance/today` | `attendance.view.*` | Get today's overview |
| POST | `/attendance/check-in` | `attendance.check_in` | Check in |
| POST | `/attendance/check-out` | `attendance.check_out` | Check out |
| GET | `/attendance` | `attendance.view.*` | List attendance records |
| POST | `/attendance/{log_id}/corrections` | `attendance.correct` | Request attendance correction |

**Query Parameters**:
- `start_date` (optional): Date range start
- `end_date` (optional): Date range end
- `employee_id` (optional): Filter by employee

**Permission Levels**:
- `attendance.view.own` - View own records
- `attendance.view.team` - View team records
- `attendance.view.all` - View all records

---

### 2.4 Leave Endpoints
**File**: `backend/app/api/v1/endpoints/leave.py`

| Method | Endpoint | Permission | Purpose |
|--------|----------|-----------|---------|
| GET | `/leave/meta` | `leave.apply` or `leave.view.*` | Get leave types and balances |
| GET | `/leave/requests` | `leave.view.*` or `leave.approve` | List leave requests |
| POST | `/leave/requests` | `leave.apply` | Apply for leave |
| POST | `/leave/requests/{leave_request_id}/decision` | `leave.approve` or `leave.recommend` | Approve/Reject leave |

**Query Parameters**:
- `status` (optional): Filter by request status
- `employee_id` (optional): Filter by employee

---

## 3. FRONTEND COMPONENTS

### 3.1 Pages Structure
**Directory**: `frontend/src/pages/`

```
pages/
├── employees/
│   └── EmployeesPage.jsx
├── attendance/
│   └── AttendancePage.jsx
├── leave/
│   └── LeavePage.jsx
├── dashboard/
├── payroll/
├── reports/
├── settings/
├── tracker/
├── notifications/
├── calendar/
├── auth/
├── ModulePlaceholderPage.jsx
└── UnauthorizedPage.jsx
```

---

### 3.2 EmployeesPage.jsx
**File**: `frontend/src/pages/employees/EmployeesPage.jsx`

**Features**:
- List all employees with search and filtering
- Create new employee (if permission allows)
- Edit existing employee details
- Update employee status (activate/deactivate)
- Assign reporting manager
- Permission-based UI (canCreate, canEdit, canDeactivate, canActivate)
- Event-based update notification system

**State Management**:
- `employees` - List of employees
- `meta` - Metadata (roles, departments, designations, managers)
- `showEmployeeForm` - Modal visibility
- `formMode` - "create" or "edit"
- `formState` - Current form data
- `selectedEmployeeId` - For edit mode
- `feedback` - Success/error messages

**Data Fetching**:
- `fetchEmployeeMeta()` - Get catalogs
- `fetchEmployees(params)` - List with filters
- `fetchEmployeeDetail(id)` - Get single employee
- `createEmployee(payload)` - Create new
- `updateEmployee(id, payload)` - Update
- `updateEmployeeStatus(id, isActive)` - Toggle status

**Form Fields**:
```javascript
{
  email, password, first_name, last_name, role_id,
  employee_code, department_id, designation_id, manager_id,
  joining_date, date_of_birth, phone_number, address,
  base_salary, is_billable
}
```

---

### 3.3 AttendancePage.jsx
**File**: `frontend/src/pages/attendance/AttendancePage.jsx`

**Features**:
- View today's attendance overview
- Check-in / Check-out functionality
- List attendance records with date range filtering
- Request attendance corrections
- Dynamic date range visualization (calendar grid)
- Attendance status display (Present, Absent, Leave, Half Day)
- Multiple filter modes (Today, Last 7 days, Current Month, Custom)

**State Management**:
- `todayOverview` - Current day status
- `records` - Attendance records
- `filters` - Date range and employee filters
- `dateFilterMode` - Filter mode selection
- `correctionTarget` - Correction form target
- `correctionForm` - Correction request data

**Data Fetching**:
- `fetchAttendanceMeta()` - Get metadata
- `fetchTodayAttendance()` - Get today's status
- `fetchAttendance(params)` - List records
- `checkIn()` - Check-in action
- `checkOut()` - Check-out action
- `correctAttendance(logId, payload)` - Request correction

**Attendance Statuses**:
- "present" → "Active" (green)
- "absent" → "Absent" (red)
- "leave" → "Leave" (blue)
- "half_day" → "Half Day" (yellow)

**Key Logic**:
- Dynamic date column generation
- Work hours calculation and formatting
- Deduplication of attendance records
- Avatar generation with consistent coloring
- Late entry detection

---

### 3.4 LeavePage.jsx
**File**: `frontend/src/pages/leave/LeavePage.jsx`

**Features**:
- View leave balances
- Apply for leave
- List leave requests with status filter
- Approve/Reject pending leave requests
- Display statistics (leave types, pending, approved, rejected)

**State Management**:
- `meta` - Leave types and balances
- `requests` - Leave requests
- `statusFilter` - Filter by status
- `formState` - Leave application form
- `feedback` - Success/error messages

**Data Fetching**:
- `fetchLeaveMeta()` - Get leave types and balances
- `fetchLeaveRequests(params)` - List requests
- `applyLeave(payload)` - Submit leave request
- `decideLeave(requestId, decision)` - Approve/Reject

**Leave Request Form**:
```javascript
{
  leave_type_id, start_date, end_date, reason
}
```

**Leave Decision**:
```javascript
{
  decision: "approved" | "rejected",
  remarks: string (optional)
}
```

**Permission-based Features**:
- `canApply` - Can apply for leave
- `canApprove` - Can approve/reject requests

---

### 3.5 API Client Layer
**Directory**: `frontend/src/api/`

#### employeeApi.js
```javascript
- fetchEmployees(params)
- fetchEmployeeMeta()
- fetchEmployeeDetail(employeeId)
- createEmployee(payload)
- updateEmployee(employeeId, payload)
- updateEmployeeStatus(employeeId, isActive)
```

#### attendanceApi.js
```javascript
- fetchAttendanceMeta()
- fetchTodayAttendance()
- fetchAttendance(params)
- checkIn()
- checkOut()
- correctAttendance(logId, payload)
```

#### leaveApi.js
```javascript
- fetchLeaveMeta()
- fetchLeaveRequests(params)
- applyLeave(payload)
- decideLeave(leaveRequestId, payload)
```

#### client.js
- Axios instance with base configuration
- Automatic token injection (from auth context)
- Error handling

---

## 4. DATABASE SETUP

### 4.1 Alembic Migrations
**Location**: `backend/alembic/versions/`

**Status**: No migration files found in the directory (empty). 

**Database Setup Process**:
- Tables are created automatically on application startup via SQLAlchemy
- Location: `backend/app/db/base.py` - Base declarative model
- Engine: `backend/app/db/session.py` - SQLAlchemy engine configuration
- Auto-bootstrap: Reference data is seeded if `settings.auto_bootstrap=True`
- Bootstrap script: `backend/scripts/seed_and_validate.py`

### 4.2 Database Configuration
**Files**:
- `backend/app/db/database.py` - Database initialization
- `backend/app/db/session.py` - Session management
- `backend/app/db/base.py` - Base model class

### 4.3 Key Tables Generated
```
Users & Auth:
- users
- roles
- permissions
- role_permissions
- user_permissions
- user_sessions

Employee Management:
- employees
- departments
- designations
- reporting_managers

Attendance:
- attendance_rules
- attendance_logs
- attendance_daily_summary
- attendance_corrections
- attendance_audit_logs

Leave:
- leave_types
- leave_requests
- leave_balances
- leave_approvals

Payroll:
- salary_structures
- payroll_runs
- payslips

Activity Tracking:
- devices
- tracker_sessions
- tracker_idle_logs
- tracker_heartbeats

Utilities:
- app_settings
- audit_logs
- holidays
- notifications
```

---

## 5. WHAT'S WORKING

✅ **Complete Core Functionality**:
- Employee CRUD operations with role-based access
- Employee hierarchy (Manager assignments)
- Attendance tracking (Check-in/out, Daily summaries)
- Attendance corrections with audit trails
- Leave request workflow (Apply → Approve/Reject)
- Leave balance management
- Permission-based access control
- User session management
- Device tracking
- Payroll run management

✅ **Backend**:
- Well-structured models with relationships
- Comprehensive API endpoints with proper permissions
- Service layer pattern for business logic
- Audit logging
- Soft delete support
- Transaction handling

✅ **Frontend**:
- React SPA with proper state management
- Component-based architecture
- API client abstraction
- Permission-based UI visibility
- Form validation
- Error handling and feedback
- Loading states

---

## 6. WHAT'S MISSING OR NEEDS FIXING

### 6.1 Database Migrations
❌ **Missing**: No Alembic migration files exist
- Current approach: Auto-create tables on startup
- **Recommendation**: Implement proper migrations for production deployment
- Create initial migration with all tables
- Track schema changes for deployment

### 6.2 Relationship Data in API Responses
⚠️ **Incomplete**: Some API endpoints may not return full nested data
- Example: Leave requests may not include serialized leave_type details
- Employee serialization looks complete but verify nested relationships

### 6.3 Frontend Component Completeness
⚠️ **Partial**: Dashboard, Payroll, Reports, Settings pages are placeholders
- Need to implement dashboard data visualization
- Payroll processing UI needs implementation
- Reports generation UI needs implementation
- Settings page for super admin needs implementation

### 6.4 Search & Reporting Features
⚠️ **Incomplete**: 
- Search endpoint exists but frontend integration may be limited
- Reports endpoint exists but no UI implementation
- Advanced filtering options may be limited

### 6.5 Notifications System
⚠️ **Exists but Limited**: Notification model exists but frontend UI may be placeholder
- Notification list page needs implementation
- Real-time notification delivery (WebSocket) not evident

### 6.6 Tracker Client Integration
⚠️ **Separate Module**: `tracker-client/` is a separate Windows service
- Activity monitoring appears to be working
- Integration with attendance may need verification
- Idle time tracking needs testing

### 6.7 Validation & Error Handling
⚠️ **Needs Enhancement**:
- Leave overlap validation (mentioned in UI but verify backend)
- Attendance rule validation (mentions but verify implementation)
- Client-side form validation could be more comprehensive

### 6.8 Testing
❌ **Missing**: No test files found
- Unit tests for services
- Integration tests for endpoints
- Frontend component tests

### 6.9 Documentation
⚠️ **Minimal**: Only architecture.md exists
- API documentation (Swagger integration available)
- Setup/deployment guide
- Configuration documentation

---

## 7. ENUMS & CONSTANTS

### Employee & User Status
```python
UserStatus: ACTIVE, INACTIVE
EmployeeStatus: ACTIVE, INACTIVE
```

### Attendance Status
```python
AttendanceStatus: PRESENT, ABSENT, HALF_DAY, LEAVE
```

### Leave Status
```python
LeaveRequestStatus: PENDING, APPROVED, REJECTED, CANCELLED
```

### Payroll Status
```python
PayrollRunStatus: DRAFT, PROCESSING, COMPLETED
```

### Device & Tracker Status1
```python
DeviceStatus: ACTIVE, INACTIVE
TrackerSessionStatus: ACTIVE, CLOSED
```

### Permission Categories
```python
PermissionCategory: MODULE, MENU, PAGE, ACTION, APPROVAL, CORRECTION, EXPORT, SETTING
```

---

## 8. TECHNOLOGY STACK

**Backend**:
- FastAPI (Python web framework)
- SQLAlchemy ORM
- Alembic (migration tool)
- JWT authentication
- Pydantic (data validation)

**Frontend**:
- React 18+
- Vite (build tool)
- Axios (HTTP client)
- Lucide React (icons)
- CSS (custom styling)

**Other**:
- Windows Tracker Client (Python)
- PowerShell for deployment

---

## 9. PERMISSION STRUCTURE

### Employee Permissions
```
employees.view, employees.create, employees.edit, employees.deactivate
employees.assign_manager, users.create, users.edit, users.activate, users.deactivate
```

### Attendance Permissions
```
attendance.view.own, attendance.view.team, attendance.view.all
attendance.check_in, attendance.check_out, attendance.correct
```

### Leave Permissions
```
leave.apply, leave.view.own, leave.view.team, leave.view.all
leave.approve, leave.recommend
```

---

## 10. DEPLOYMENT & SETUP

### Backend Setup
```bash
cd backend
python -m venv .venv
.venv/Scripts/Activate
pip install -r requirements.txt
python -m app.main  # Runs on http://localhost:8000
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev  # Runs on http://localhost:5173
```

### Tracker Client Setup
```bash
cd tracker-client
python -m venv .venv
.\setup.ps1  # Windows setup
python main.py
```

---

## 11. KEY FILES REFERENCE

| Purpose | File Path |
|---------|-----------|
| Employee Model | `backend/app/models/employee.py` |
| Attendance Model | `backend/app/models/attendance.py` |
| Leave Model | `backend/app/models/leave.py` |
| Employee API | `backend/app/api/v1/endpoints/employees.py` |
| Attendance API | `backend/app/api/v1/endpoints/attendance.py` |
| Leave API | `backend/app/api/v1/endpoints/leave.py` |
| Employee Service | `backend/app/services/employee_service.py` |
| Auth Service | `backend/app/services/auth_service.py` |
| Employee Page | `frontend/src/pages/employees/EmployeesPage.jsx` |
| Attendance Page | `frontend/src/pages/attendance/AttendancePage.jsx` |
| Leave Page | `frontend/src/pages/leave/LeavePage.jsx` |
| API Router | `backend/app/api/router.py` |
| Main App | `backend/app/main.py` |

---

## 12. SUMMARY CHECKLIST

| Item | Status | Notes |
|------|--------|-------|
| Employee Models | ✅ Complete | Full CRUD, relationships defined |
| Attendance Models | ✅ Complete | With corrections & audit logs |
| Leave Models | ✅ Complete | Requests, balances, approvals |
| Employee APIs | ✅ Complete | CRUD + manager assignment |
| Attendance APIs | ✅ Complete | Check-in/out + corrections |
| Leave APIs | ✅ Complete | Request + decision endpoints |
| Frontend - Employees | ✅ Complete | Full CRUD UI |
| Frontend - Attendance | ✅ Complete | Check-in/out + correction form |
| Frontend - Leave | ✅ Complete | Apply + approve/reject |
| Database Schema | ✅ Generated | Auto-created, no migrations |
| Permissions | ✅ Defined | Role + user permissions |
| Authentication | ✅ Implemented | JWT + session management |
| Error Handling | ⚠️ Partial | Could be more comprehensive |
| Testing | ❌ Missing | No test suite |
| Documentation | ⚠️ Minimal | Architecture exists, needs expansion |

