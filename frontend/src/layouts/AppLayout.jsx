import { useEffect, useRef } from "react";
import { Outlet } from "react-router-dom";
import { fetchTodayAttendance } from "../api/attendanceApi";
import { sendTrackerHeartbeat, trackerCheckIn } from "../api/trackerApi";
import HeaderBar from "../components/layout/HeaderBar";
import Sidebar from "../components/layout/Sidebar";
import useAuth from "../hooks/useAuth";
import { API_BASE_URL } from "../api/client";
import { getAccessToken } from "../utils/tokenStorage";

const ATTENDANCE_UPDATED_EVENT = "hrm:attendance-updated";
const TRACKER_HEARTBEAT_INTERVAL_MS = 30000;

function getDeviceInfo() {
  return {
    device_name: "Dashboard Session",
    source: "web",
    user_agent: window.navigator.userAgent,
    platform: window.navigator.platform,
    language: window.navigator.language,
  };
}

function postTrackerLogout(reason) {
  const accessToken = getAccessToken();
  if (!accessToken) {
    return;
  }

  const payload = JSON.stringify({
    logout_time: new Date().toISOString(),
    reason,
  });

  void fetch(`${API_BASE_URL}/tracker/logout`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: payload,
    keepalive: true,
  }).catch(() => {});
}

function AppLayout() {
  const { hasPermission, user } = useAuth();
  const isCheckedInRef = useRef(false);
  const isSyncingRef = useRef(false);
  const canSendTrackerHeartbeat = Boolean(user && hasPermission("attendance.check_in"));

  useEffect(() => {
    if (!canSendTrackerHeartbeat) {
      return undefined;
    }

    let isDisposed = false;

    async function sendHeartbeat({ forceCheckIn = false, isIdle = false } = {}) {
      if (isDisposed || !isCheckedInRef.current) {
        return;
      }
      const payload = {
        heartbeat_at: new Date().toISOString(),
        is_idle: isIdle,
        device_info: getDeviceInfo(),
      };
      try {
        if (forceCheckIn) {
          await trackerCheckIn({
            check_in_at: payload.heartbeat_at,
            device_info: payload.device_info,
          });
        } else {
          await sendTrackerHeartbeat(payload);
        }
      } catch {
        // Heartbeat failures are tolerated; stale sessions are marked offline server-side.
      }
    }

    async function syncFromAttendance() {
      if (isDisposed || isSyncingRef.current) {
        return;
      }
      isSyncingRef.current = true;
      try {
        const attendance = await fetchTodayAttendance();
        const isCheckedIn = Boolean(attendance?.log?.check_in_at && !attendance?.log?.check_out_at);
        const wasCheckedIn = isCheckedInRef.current;
        isCheckedInRef.current = isCheckedIn;

        if (isCheckedIn) {
          await sendHeartbeat({ forceCheckIn: !wasCheckedIn });
        } else if (wasCheckedIn) {
          postTrackerLogout("checkout");
        }
      } catch {
        // Normal dashboard error handling will surface auth/API issues.
      } finally {
        isSyncingRef.current = false;
      }
    }

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        void syncFromAttendance();
      }
    }

    void syncFromAttendance();
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void sendHeartbeat();
      }
    }, TRACKER_HEARTBEAT_INTERVAL_MS);

    window.addEventListener(ATTENDANCE_UPDATED_EVENT, syncFromAttendance);
    window.addEventListener("focus", syncFromAttendance);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      isDisposed = true;
      window.clearInterval(intervalId);
      window.removeEventListener(ATTENDANCE_UPDATED_EVENT, syncFromAttendance);
      window.removeEventListener("focus", syncFromAttendance);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [canSendTrackerHeartbeat]);

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-main" style={{ marginLeft: "var(--sidebar-w)" }}>
        <HeaderBar />
        <main className="content-area">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
