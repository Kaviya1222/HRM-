# Windows Tracker Client

This folder contains the Python-based desktop/background tracker agent scaffold.

## Responsibilities

- auto-run on Windows startup through Task Scheduler
- register the device with the HRM backend
- start and close user sessions
- detect idle start and idle end events
- send periodic heartbeat signals
- queue unsent events locally when offline
- replay cached events when connectivity returns

## Key modules

- `main.py`: tracker runtime coordinator
- `config.py`: runtime configuration
- `api/client.py`: authenticated API wrapper
- `services/`: device, session, idle, heartbeat, startup services
- `utils/cache.py`: offline sqlite queue
- `utils/system.py`: hostname, username, device UUID, idle-time helpers
- `startup/register_task.ps1`: Task Scheduler registration script

## Startup strategy

Task Scheduler is preferred over a startup shortcut because it is more reliable for:

- run-at-logon behavior
- failure recovery
- explicit task naming
- controlled user context execution

## Current state

The tracker code is scaffolded and ready to connect to the dedicated tracker endpoints in the next implementation phase.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The compiled executable is created at `dist\hrm-tracker.exe`.
