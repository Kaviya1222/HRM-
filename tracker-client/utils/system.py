from __future__ import annotations

import ctypes
import getpass
import hashlib
import platform
import socket
import subprocess
from ctypes import wintypes


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_hostname() -> str:
    return socket.gethostname()


def get_username() -> str:
    return getpass.getuser()


def get_os_version() -> str:
    return f"{platform.system()} {platform.release()}"


def get_device_uuid() -> str:
    try:
        result = subprocess.run(
            ["wmic", "csproduct", "get", "uuid"],
            capture_output=True,
            check=True,
            text=True,
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip() and "UUID" not in line]
        if lines:
            return lines[0]
    except Exception:
        pass

    fallback = f"{get_hostname()}::{platform.node()}::{platform.machine()}"
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def get_idle_seconds() -> int:
    if platform.system().lower() != "windows":
        return 0

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)

    if not user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        return 0

    millis = kernel32.GetTickCount() - last_input_info.dwTime
    return max(int(millis / 1000), 0)
