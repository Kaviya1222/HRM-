import { useEffect, useMemo, useState } from "react";
import { Monitor, RefreshCw, ShieldCheck, Wifi } from "lucide-react";
import { fetchTrackerLiveStatus } from "../../api/trackerApi";

function formatDateTime(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("en-IN");
}

function formatStatus(value) {
  if (!value) {
    return "Offline";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function getTrackerActivityTime(row) {
  const value = row.last_heartbeat || row.login_time || row.logout_time;
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function sortTrackerRows(items = []) {
  return [...items].sort((left, right) => {
    const leftOnline = left.active_status === "online" ? 1 : 0;
    const rightOnline = right.active_status === "online" ? 1 : 0;
    if (leftOnline !== rightOnline) {
      return rightOnline - leftOnline;
    }
    return getTrackerActivityTime(right) - getTrackerActivityTime(left);
  });
}

function TrackerPage() {
  const [rows, setRows] = useState([]);
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const stats = useMemo(() => {
    const online = new Set(
      rows
        .filter((row) => row.active_status === "online")
        .map((row) => row.employee_id || row.user_id || row.tracker_session_id),
    ).size;
    const offline = Math.max(rows.length - online, 0);
    return [
      { label: "Total Employees", value: rows.length },
      { label: "Online Employees", value: online },
      { label: "Offline Employees", value: offline },
    ];
  }, [rows]);

  async function loadTrackerData({ silent = false } = {}) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const response = await fetchTrackerLiveStatus();
      setRows(sortTrackerRows(response.items || []));
      setFeedback({ type: "", message: "" });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to load tracker monitor data.",
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadTrackerData();
    const intervalId = window.setInterval(() => {
      loadTrackerData({ silent: true });
    }, 10000);
    return () => window.clearInterval(intervalId);
  }, []);

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading tracker monitor...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <Monitor size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Tracker Monitoring</h2>
          <p className="page-section-header-sub">
            View employee check-in sessions, heartbeat freshness, activity status, and device details from live tracker activity.
          </p>
        </div>
      </div>

      {feedback.message ? (
        <div className={`employee-feedback employee-feedback--${feedback.type || "info"}`}>
          <ShieldCheck size={16} />
          <span>{feedback.message}</span>
        </div>
      ) : null}

      <div className="employee-stats-grid">
        {stats.map((card) => (
          <div className="employee-stat-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>

      <section className="employee-panel">
        <div className="module-toolbar">
          <div>
            <p className="sidebar-section-label">Live Monitor</p>
            <h3 className="module-panel-title">Tracker sessions</h3>
          </div>
          <button className="ghost-button" onClick={() => loadTrackerData({ silent: true })} type="button">
            <RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
            Refresh
          </button>
        </div>

        <div className="employee-table-wrap">
          <table className="employee-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Login Time</th>
                <th>Last Heartbeat</th>
                <th>Idle Minutes</th>
                <th>Status</th>
                <th>Device</th>
                <th>Logout Time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.tracker_session_id}>
                  <td>
                    <div className="employee-primary-cell">
                      <strong>{row.employee_name}</strong>
                      <span>{row.employee_code}</span>
                    </div>
                  </td>
                  <td>{formatDateTime(row.login_time)}</td>
                  <td>{formatDateTime(row.last_heartbeat)}</td>
                  <td>{row.idle_minutes}</td>
                  <td>
                    <span className={`status-chip status-chip--${row.active_status}`}>
                      {formatStatus(row.active_status)}
                    </span>
                  </td>
                  <td>{row.device_name} ({row.system || "Unknown"})</td>
                  <td>{formatDateTime(row.logout_time)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {!rows.length ? (
            <div className="employee-empty-state">
              <Wifi size={18} />
              <span>No tracker activity is available yet.</span>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default TrackerPage;
