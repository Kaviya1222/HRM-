# HRM Monorepo

Production-oriented Human Resource Management system built with:

- Frontend: React.js
- Backend: FastAPI + SQLAlchemy + Alembic
- Database: PostgreSQL
- Windows client tracker: Python background agent

Current implementation focus:

1. overall architecture and schema design
2. backend project foundation
3. authentication module
4. Super Admin settings and dynamic permission system
5. frontend auth flow and permission-aware app shell
6. tracker client scaffolding and technical design

## Repository layout

```text
backend/         FastAPI application, models, services, migrations
frontend/        React application with protected routes and settings UI
tracker-client/  Windows tracker agent scaffold
docs/            Architecture, schema, and implementation notes
```

## Local Quick Start

Prerequisites:

- Python 3.11
- Node.js 20 or newer
- MySQL 8 or compatible local MySQL server

Run MySQL locally. The backend creates the `hrm_db` database automatically when it connects with the configured local credentials:

```powershell
mysql -u root -proot
```

Set up environment values:

```powershell
Copy-Item .env.example .env
```

Install and run the backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Install and run the frontend in a separate terminal:

```powershell
cd frontend
npm install
npm run dev
```

Services:

- frontend: `http://localhost:5173`
- backend: `http://localhost:8000`
- API health check: `http://localhost:8000/health`
- mysql: `localhost:3306`

The backend reads environment values from the repository root `.env`. The frontend uses `VITE_API_BASE_URL` from the same file value; keep it set to `http://localhost:8000/api/v1` for local development.

## Tracker quick start

Set up the tracker development environment:

```powershell
cd tracker-client
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Build the Windows tracker executable:

```powershell
cd tracker-client
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

## Role hierarchy

The system enforces this exact role order throughout the design:

`Super Admin -> Admin -> HR -> TL -> Employee`

`Super Admin` is always the highest authority and always has full system access. All other access is dynamically assigned through the Super Admin settings module and enforced in both backend and frontend.

## Implemented foundations

- clean backend layering: `api`, `services`, `schemas`, `models`, `permissions`, `core`
- JWT login, refresh, logout, current-user session handling
- bcrypt password hashing
- dynamic role-permission catalog and effective permission evaluation
- Super Admin settings APIs for role permission management and app settings
- React login page, auth store, protected routing, permission-aware navigation
- Super Admin settings page for permission matrix management
- tracker client modular structure for registration, session, idle, heartbeat, and offline sync

## Core documents

- [Architecture and schema](docs/architecture.md)

## Next phases

After this foundation, the next module sequence should remain:

1. employee management
2. attendance
3. leave management
4. dashboard and reporting
5. payroll
6. tracker synchronization and monitoring UI
