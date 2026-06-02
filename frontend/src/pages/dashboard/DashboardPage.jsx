import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Banknote,
  Bell,
  CalendarCheck,
  CalendarClock,
  Clock3,
  RefreshCw,
  Users,
  Wallet,
} from "lucide-react";
import { fetchDashboardSummary } from "../../api/dashboardApi";
import { checkIn, checkOut, fetchTodayAttendance } from "../../api/attendanceApi";
import useAuth from "../../hooks/useAuth";

ChartJS.register(
  ArcElement,
  BarElement,
  CategoryScale,
  Filler,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
);

const METRIC_ICON_MAP = {
  present_today: CalendarCheck,
  total_employees: Users,
  today_attendance_pct: CalendarCheck,
  late_comers_count: Clock3,
  absent_count: AlertTriangle,
  half_day_count: CalendarClock,
  employees_on_leave_today: CalendarClock,
  pending_leave_approvals: Bell,
  total_leaves: CalendarClock,
  approved_leaves: CalendarCheck,
  rejected_leaves: AlertTriangle,
  payroll_pending_tasks: Wallet,
  payroll_total_income: Banknote,
  payroll_total_expense: Wallet,
  payroll_total_balance: Wallet,
  total_salary_expense_month: Banknote,
  total_salary_processed_month: Banknote,
  employees_missing_salary_setup: Users,
  current_month_payroll_status: Wallet,
  pending_payments: Wallet,
};

const ATTENDANCE_UPDATED_EVENT = "hrm:attendance-updated";
const ATTENDANCE_UPDATED_AT_KEY = "hrm:attendance-updated-at";
const PAYROLL_UPDATED_EVENT = "hrm:payroll-updated";
const PAYROLL_UPDATED_AT_KEY = "hrm:payroll-updated-at";
const CALENDAR_UPDATED_EVENT = "hrm:calendar-updated";
const CALENDAR_UPDATED_AT_KEY = "hrm:calendar-updated-at";
const LEAVE_UPDATED_EVENT = "hrm:leave-updated";
const LEAVE_UPDATED_AT_KEY = "hrm:leave-updated-at";

const EMPTY_SUMMARY = {
  cards: [],
  meta: {
    upcoming_events_count: 0,
  },
  charts: {
    working_hours: { labels: [], total_hours: [], average_hours: [] },
    leave_usage: { labels: [], values: [], by_type: [] },
    attendance_trend: { labels: [], present: [], leave: [], absent: [] },
  },
  monthly_attendance_preview: [],
  kpi_table_rows: [],
  upcoming_events: [],
};

const CHART_COLORS = {
  amber: "rgba(217, 167, 103, 0.92)",
  amberSoft: "rgba(217, 167, 103, 0.18)",
  blue: "rgba(59, 130, 246, 0.95)",
  blueSoft: "rgba(59, 130, 246, 0.16)",
  green: "rgba(34, 197, 94, 0.92)",
  greenSoft: "rgba(34, 197, 94, 0.16)",
  red: "rgba(239, 68, 68, 0.92)",
  redSoft: "rgba(239, 68, 68, 0.16)",
  violet: "rgba(167, 139, 250, 0.92)",
  violetSoft: "rgba(167, 139, 250, 0.18)",
  cyan: "rgba(56, 189, 248, 0.9)",
};

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    intersect: false,
    mode: "index",
  },
  plugins: {
    legend: {
      labels: {
        color: "#cbd5e1",
        boxWidth: 12,
        usePointStyle: true,
        pointStyle: "circle",
      },
    },
    tooltip: {
      backgroundColor: "rgba(12, 18, 30, 0.96)",
      borderColor: "rgba(255,255,255,0.08)",
      borderWidth: 1,
      titleColor: "#f8fafc",
      bodyColor: "#cbd5e1",
      padding: 12,
    },
  },
  scales: {
    x: {
      ticks: { color: "#94a3b8" },
      grid: { display: false },
    },
    y: {
      ticks: { color: "#94a3b8" },
      grid: { color: "rgba(148, 163, 184, 0.12)" },
      beginAtZero: true,
    },
  },
};

function formatEventDate(value) {
  const dateValue = new Date(value);
  return {
    day: dateValue.toLocaleDateString("en-IN", { day: "2-digit" }),
    month: dateValue.toLocaleDateString("en-IN", { month: "short" }).toUpperCase(),
    weekday: dateValue.toLocaleDateString("en-IN", { weekday: "long" }),
  };
}

function formatDisplayDate(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDuration(totalSeconds) {
  const safeSeconds = Math.max(Number(totalSeconds) || 0, 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatLocalDateTime(value) {
  const dateValue = value instanceof Date ? value : new Date(value);
  const year = dateValue.getFullYear();
  const month = String(dateValue.getMonth() + 1).padStart(2, "0");
  const day = String(dateValue.getDate()).padStart(2, "0");
  const hours = String(dateValue.getHours()).padStart(2, "0");
  const minutes = String(dateValue.getMinutes()).padStart(2, "0");
  const seconds = String(dateValue.getSeconds()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

function getCompletedWorkedSeconds(log) {
  if (!log) {
    return 0;
  }
  const sessions = Array.isArray(log.sessions) ? log.sessions : [];
  const completedSeconds = sessions
    .filter((session) => session?.check_in_at && session?.check_out_at)
    .reduce((total, session) => {
      if (session.work_seconds != null) {
        return total + Number(session.work_seconds || 0);
      }
      return total + Number(session.work_minutes || 0) * 60;
    }, 0);
  if (completedSeconds) {
    return completedSeconds;
  }
  if (log.work_seconds != null) {
    return Number(log.work_seconds || 0);
  }
  return Number(log.work_minutes || 0) * 60;
}

function DashboardPage() {
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [todayAttendance, setTodayAttendance] = useState({ status: "absent", log: null, can_check_in: false, can_check_out: false });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAttendanceActionLoading, setIsAttendanceActionLoading] = useState(false);
  const [timerNow, setTimerNow] = useState(() => Date.now());
  const [timerStartedAt, setTimerStartedAt] = useState(null);
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [attendanceStatus, setAttendanceStatus] = useState("idle");
  const [checkedIn, setCheckedIn] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [showTimer, setShowTimer] = useState(false);
  const [error, setError] = useState("");
  const [attendanceActionMessage, setAttendanceActionMessage] = useState("");
  const attendanceActionInFlightRef = useRef(false);
  const localCheckInAtRef = useRef(null);
  const sessionBaseElapsedRef = useRef(0);

  function syncAttendanceState(attendanceData) {
    const log = attendanceData?.log || null;
    const hasCheckIn = Boolean(log?.check_in_at);
    const hasCheckOut = Boolean(log?.check_out_at);
    const isActivePunch = hasCheckIn && !hasCheckOut;
    const completedSeconds = getCompletedWorkedSeconds(log);
    const activeCheckInAt = isActivePunch ? new Date(log.check_in_at) : null;
    const activeElapsedSeconds = activeCheckInAt && !Number.isNaN(activeCheckInAt.getTime())
      ? Math.max(Math.floor((Date.now() - activeCheckInAt.getTime()) / 1000), 0)
      : 0;

    setCheckedIn(isActivePunch);
    setAttendanceStatus(isActivePunch ? "checked_in" : "idle");
    setIsTimerRunning(isActivePunch);
    setTimerStartedAt(null);
    setElapsedSeconds(isActivePunch ? completedSeconds + activeElapsedSeconds : completedSeconds);
    sessionBaseElapsedRef.current = completedSeconds;
    localCheckInAtRef.current = activeCheckInAt;
    setShowTimer(isActivePunch);
    setTimerNow(Date.now());
  }

  async function loadSummary({ silent = false, syncAttendance = true } = {}) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const [response, attendanceResponse] = await Promise.all([
        fetchDashboardSummary(),
        fetchTodayAttendance(),
      ]);
      setSummary({
        ...EMPTY_SUMMARY,
        ...response,
        charts: {
          ...EMPTY_SUMMARY.charts,
          ...response.charts,
        },
      });
      setTodayAttendance(attendanceResponse);
      if (syncAttendance) {
        syncAttendanceState(attendanceResponse);
      }
      setError("");
    } catch (loadError) {
      setError(loadError.response?.data?.detail || "Unable to load dashboard summary.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadSummary();
  }, []);

  useEffect(() => {
    if (!checkedIn) {
      return undefined;
    }

    const timerId = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1);
    }, 1000);

    return () => window.clearInterval(timerId);
  }, [checkedIn]);

  useEffect(() => {
    function refreshDashboardSummary() {
      void loadSummary({ silent: true });
    }

    function handleStorage(event) {
      if ([ATTENDANCE_UPDATED_AT_KEY, PAYROLL_UPDATED_AT_KEY, CALENDAR_UPDATED_AT_KEY, LEAVE_UPDATED_AT_KEY].includes(event.key)) {
        refreshDashboardSummary();
      }
    }

    window.addEventListener(ATTENDANCE_UPDATED_EVENT, refreshDashboardSummary);
    window.addEventListener(PAYROLL_UPDATED_EVENT, refreshDashboardSummary);
    window.addEventListener(CALENDAR_UPDATED_EVENT, refreshDashboardSummary);
    window.addEventListener(LEAVE_UPDATED_EVENT, refreshDashboardSummary);
    window.addEventListener("storage", handleStorage);
    window.addEventListener("focus", refreshDashboardSummary);

    return () => {
      window.removeEventListener(ATTENDANCE_UPDATED_EVENT, refreshDashboardSummary);
      window.removeEventListener(PAYROLL_UPDATED_EVENT, refreshDashboardSummary);
      window.removeEventListener(CALENDAR_UPDATED_EVENT, refreshDashboardSummary);
      window.removeEventListener(LEAVE_UPDATED_EVENT, refreshDashboardSummary);
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("focus", refreshDashboardSummary);
    };
  }, []);

  const timeGreeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good Morning";
    if (hour < 17) return "Good Afternoon";
    return "Good Evening";
  })();

  const displayedWorkedSeconds = elapsedSeconds;
  const canCheckIn = hasPermission("attendance.check_in");
  const canCheckOut = hasPermission("attendance.check_out");
  const canUseAttendanceAction = checkedIn
    ? canCheckOut && todayAttendance.can_check_out
    : canCheckIn && todayAttendance.can_check_in;
  const attendanceButtonLabel = checkedIn ? "Check Out" : "Check In";
  const attendanceButtonIcon = checkedIn ? <Clock3 size={14} /> : <CalendarCheck size={14} />;
  const isAttendanceButtonDisabled = isAttendanceActionLoading || !canUseAttendanceAction;

  async function handleDashboardCheckIn() {
    if (!canCheckIn || attendanceActionInFlightRef.current || attendanceStatus !== "idle") {
      return;
    }
    attendanceActionInFlightRef.current = true;
    setIsAttendanceActionLoading(true);
    setAttendanceActionMessage("");
    setError("");
    localStorage.removeItem("hrm:attendance-timer-started-at");
    localStorage.removeItem("hrm:attendance-timer-elapsed");
    sessionStorage.removeItem("hrm:attendance-timer-started-at");
    sessionStorage.removeItem("hrm:attendance-timer-elapsed");
    const checkInAt = new Date();
    const baseElapsedSeconds = getCompletedWorkedSeconds(todayAttendance.log);
    sessionBaseElapsedRef.current = baseElapsedSeconds;
    localCheckInAtRef.current = checkInAt;
    setElapsedSeconds(baseElapsedSeconds);
    setCheckedIn(true);
    setAttendanceStatus("checked_in");
    setShowTimer(true);
    setTodayAttendance((current) => ({
      ...current,
      status: "present",
      log: {
        ...(current.log || {}),
        check_in_at: formatLocalDateTime(checkInAt),
        check_out_at: null,
        status: "present",
        work_minutes: 0,
        work_seconds: 0,
      },
      can_check_in: false,
      can_check_out: true,
    }));
    setTimerStartedAt(checkInAt.getTime());
    setIsTimerRunning(true);
    setTimerNow(Date.now());

    try {
      const response = await checkIn({ check_in_at: formatLocalDateTime(checkInAt) });
      const hasCheckedOut = Boolean(response.log?.check_out_at);
      setTodayAttendance((current) => ({
        ...current,
        status: response.log?.status || "present",
        log: response.log || current.log,
        can_check_in: false,
        can_check_out: !hasCheckedOut,
      }));
      if (hasCheckedOut) {
        syncAttendanceState({
          status: response.log?.status || "present",
          log: response.log,
        });
      } else {
        setCheckedIn(true);
        setAttendanceStatus("checked_in");
        setIsTimerRunning(true);
        setShowTimer(true);
      }
      setAttendanceActionMessage(response.message || "Checked in successfully.");
      const updatedAt = String(Date.now());
      localStorage.setItem(ATTENDANCE_UPDATED_AT_KEY, updatedAt);
      window.dispatchEvent(new CustomEvent(ATTENDANCE_UPDATED_EVENT, { detail: { updatedAt } }));
      void loadSummary({ silent: true, syncAttendance: false });
    } catch (actionError) {
      setError(actionError.response?.data?.detail || "Unable to check in.");
      setIsTimerRunning(false);
      setTimerStartedAt(null);
      setCheckedIn(false);
      setAttendanceStatus("idle");
      void loadSummary({ silent: true });
    } finally {
      setIsAttendanceActionLoading(false);
      attendanceActionInFlightRef.current = false;
    }
  }

  async function handleDashboardCheckOut() {
    if (!canCheckOut || attendanceActionInFlightRef.current || attendanceStatus !== "checked_in") {
      return;
    }
    if (todayAttendance.log?.check_out_at) {
      setCheckedIn(false);
      setAttendanceStatus("idle");
      setIsTimerRunning(false);
      setTimerStartedAt(null);
      setTimerNow(Date.now());
      setError("");
      setAttendanceActionMessage("Already checked out today");
      return;
    }
    attendanceActionInFlightRef.current = true;
    setIsAttendanceActionLoading(true);
    setAttendanceActionMessage("");
    setError("");
    setCheckedIn(false);
    const checkOutAt = new Date();
    const localCheckInAt = localCheckInAtRef.current;
    const sessionElapsedSeconds = localCheckInAt
      ? Math.max(Math.floor((checkOutAt.getTime() - localCheckInAt.getTime()) / 1000), 0)
      : Math.max(elapsedSeconds - sessionBaseElapsedRef.current, 0);
    setTodayAttendance((current) => ({
      ...current,
      log: current.log?.check_in_at
        ? {
          ...current.log,
          check_out_at: formatLocalDateTime(checkOutAt),
        }
        : current.log,
      can_check_in: false,
      can_check_out: false,
    }));
    setIsTimerRunning(false);
    setTimerStartedAt(null);
    setCheckedIn(false);
    setAttendanceStatus("idle");
    setTimerNow(Date.now());

    try {
      const response = await checkOut({
        check_in_at: localCheckInAt ? formatLocalDateTime(localCheckInAt) : undefined,
        check_out_at: formatLocalDateTime(checkOutAt),
        elapsed_seconds: sessionElapsedSeconds,
      });
      const nextCompletedSeconds = sessionBaseElapsedRef.current + sessionElapsedSeconds;
      setTodayAttendance((current) => ({
        ...current,
        status: response.log?.status || current.status,
        log: response.log || current.log,
        can_check_in: false,
        can_check_out: false,
      }));
      setElapsedSeconds(nextCompletedSeconds);
      sessionBaseElapsedRef.current = nextCompletedSeconds;
      setShowTimer(false);
      localCheckInAtRef.current = null;
      setAttendanceActionMessage(response.message || "Checked out successfully.");
      const updatedAt = String(Date.now());
      localStorage.setItem(ATTENDANCE_UPDATED_AT_KEY, updatedAt);
      window.dispatchEvent(new CustomEvent(ATTENDANCE_UPDATED_EVENT, { detail: { updatedAt } }));
      void loadSummary({ silent: true, syncAttendance: false });
    } catch (actionError) {
      const detail = actionError.response?.data?.detail || "";
      if (detail === "Already checked out today" || detail === "Employee has already checked out today") {
        setError("");
        setIsTimerRunning(false);
        setTimerStartedAt(null);
        setCheckedIn(false);
        setAttendanceStatus("idle");
        setShowTimer(false);
        setTimerNow(Date.now());
        setAttendanceActionMessage("Already checked out today");
      } else {
        setError(detail || "Unable to check out.");
        setIsTimerRunning(true);
        setTimerStartedAt(Date.now() - elapsedSeconds * 1000);
        setCheckedIn(true);
        setAttendanceStatus("checked_in");
      }
      void loadSummary({ silent: true });
    } finally {
      setIsAttendanceActionLoading(false);
      attendanceActionInFlightRef.current = false;
    }
  }

  const workingHoursData = useMemo(() => ({
    labels: summary.charts.working_hours.labels,
    datasets: [
      {
        label: "Total Working Hours",
        data: summary.charts.working_hours.total_hours,
        borderRadius: 8,
        backgroundColor: CHART_COLORS.amber,
        maxBarThickness: 36,
      },
      {
        label: "Average Hours / Employee",
        data: summary.charts.working_hours.average_hours,
        borderRadius: 8,
        backgroundColor: CHART_COLORS.blue,
        maxBarThickness: 20,
      },
    ],
  }), [summary.charts.working_hours]);

  const leaveUsageData = useMemo(() => ({
    labels: summary.charts.leave_usage.labels,
    datasets: [
      {
        label: "Leave Days Used",
        data: summary.charts.leave_usage.values,
        borderRadius: 10,
        backgroundColor: [
          "rgba(217, 167, 103, 0.92)",
          "rgba(56, 189, 248, 0.92)",
          "rgba(167, 139, 250, 0.92)",
          "rgba(34, 197, 94, 0.92)",
          "rgba(239, 68, 68, 0.92)",
          "rgba(244, 114, 182, 0.92)",
        ],
      },
    ],
  }), [summary.charts.leave_usage]);

  const leaveBreakdownData = useMemo(() => ({
    labels: summary.charts.leave_usage.by_type.map((item) => item.label),
    datasets: [
      {
        data: summary.charts.leave_usage.by_type.map((item) => item.value),
        borderWidth: 0,
        backgroundColor: [
          "rgba(217, 167, 103, 0.95)",
          "rgba(56, 189, 248, 0.95)",
          "rgba(167, 139, 250, 0.95)",
          "rgba(34, 197, 94, 0.95)",
        ],
      },
    ],
  }), [summary.charts.leave_usage.by_type]);

  const attendanceTrendData = useMemo(() => ({
    labels: summary.charts.attendance_trend.labels,
    datasets: [
      {
        label: "Present",
        data: summary.charts.attendance_trend.present,
        tension: 0.35,
        borderColor: CHART_COLORS.green,
        backgroundColor: CHART_COLORS.greenSoft,
        pointRadius: 3,
        fill: true,
      },
      {
        label: "Leave",
        data: summary.charts.attendance_trend.leave,
        tension: 0.35,
        borderColor: CHART_COLORS.violet,
        backgroundColor: CHART_COLORS.violetSoft,
        pointRadius: 3,
        fill: true,
      },
      {
        label: "Absent",
        data: summary.charts.attendance_trend.absent,
        tension: 0.35,
        borderColor: CHART_COLORS.red,
        backgroundColor: CHART_COLORS.redSoft,
        pointRadius: 3,
        fill: true,
      },
    ],
  }), [summary.charts.attendance_trend]);

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading dashboard...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container dashboard-page">
      <section className="dashboard-attendance-strip">
        <div className="dashboard-hero-actions">
          <div className="dashboard-attendance-control">
            <div className="dashboard-attendance-actions">
              <button
                className={`dashboard-attendance-button ${
                  checkedIn ? "dashboard-attendance-button--check-out" : "dashboard-attendance-button--check-in"
                }`}
                disabled={isAttendanceButtonDisabled}
                onClick={checkedIn ? handleDashboardCheckOut : handleDashboardCheckIn}
                type="button"
              >
                {attendanceButtonIcon}
                {attendanceButtonLabel}
              </button>
            </div>
            {showTimer ? (
              <div className="dashboard-attendance-timer">
                <strong>{formatDuration(displayedWorkedSeconds)}</strong>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <h2 className="dashboard-hero-title">{timeGreeting}</h2>
        </div>

        <div className="dashboard-hero-meta">
          <div className="dashboard-hero-date">
            {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
          </div>
          <button className="ghost-button" onClick={() => loadSummary({ silent: true })} type="button">
            <RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
            Refresh Data
          </button>
        </div>
      </section>

      {error ? (
        <div className="employee-feedback employee-feedback--error">
          <AlertTriangle size={16} />
          <span>{error}</span>
        </div>
      ) : null}

      {attendanceActionMessage ? (
        <div className="employee-feedback employee-feedback--success">
          <CalendarCheck size={16} />
          <span>{attendanceActionMessage}</span>
        </div>
      ) : null}

      <section className="dashboard-metrics-grid">
        {summary.cards.map((card) => {
          const Icon = METRIC_ICON_MAP[card.key] || Users;
          const isLinkedCard = Boolean(card.target_url);
          return (
            <article
              className={`dashboard-metric-card dashboard-metric-card--${card.accent || "blue"}`}
              key={card.key}
              onClick={isLinkedCard ? () => navigate(card.target_url) : undefined}
              onKeyDown={isLinkedCard ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  navigate(card.target_url);
                }
              } : undefined}
              role={isLinkedCard ? "link" : undefined}
              tabIndex={isLinkedCard ? 0 : undefined}
            >
              <div className="dashboard-metric-icon">
                <Icon size={20} />
              </div>
              <div className="dashboard-metric-content">
                <span className="dashboard-metric-label">{card.label}</span>
                <strong className="dashboard-metric-value">{card.display_value || card.value}</strong>
                <span className="dashboard-metric-helper">{card.helper}</span>
              </div>
            </article>
          );
        })}
      </section>

      <section className="dashboard-analytics-grid">
        <article className="dashboard-chart-card dashboard-chart-card--wide">
          <div className="dashboard-section-header">
            <div>
              <p className="sidebar-section-label">Working Hours Analysis</p>
              <h3 className="module-panel-title">Daily working hour patterns</h3>
            </div>
            <span className="dashboard-section-note">Last 7 days</span>
          </div>
          <div className="dashboard-chart-wrap">
            <Bar data={workingHoursData} options={chartOptions} />
          </div>
        </article>

        <article className="dashboard-chart-card">
          <div className="dashboard-section-header">
            <div>
              <p className="sidebar-section-label">Attendance Trend</p>
              <h3 className="module-panel-title">Present vs leave vs absent</h3>
            </div>
            <span className="dashboard-section-note">Last 1 month</span>
          </div>
          <div className="dashboard-chart-wrap">
            <Line data={attendanceTrendData} options={chartOptions} />
          </div>
        </article>

        <article className="dashboard-chart-card dashboard-chart-card--wide">
          <div className="dashboard-section-header">
            <div>
              <p className="sidebar-section-label">Leave Usage</p>
              <h3 className="module-panel-title">Monthly leave usage and type mix</h3>
            </div>
            <span className="dashboard-section-note">Rolling 6 months</span>
          </div>

          <div className="dashboard-chart-split">
            <div className="dashboard-chart-wrap dashboard-chart-wrap--compact">
              <Bar data={leaveUsageData} options={chartOptions} />
            </div>

            <div className="dashboard-donut-panel">
              {summary.charts.leave_usage.by_type.length ? (
                <>
                  <div className="dashboard-donut-wrap">
                    <Doughnut
                      data={leaveBreakdownData}
                      options={{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                          legend: {
                            position: "bottom",
                            labels: {
                              color: "#cbd5e1",
                              boxWidth: 10,
                              padding: 16,
                            },
                          },
                        },
                        cutout: "68%",
                      }}
                    />
                  </div>
                  <span className="dashboard-section-note">By leave type</span>
                </>
              ) : (
                <div className="employee-empty-state">
                  <CalendarClock size={18} />
                  <span>No approved leave usage has been recorded yet.</span>
                </div>
              )}
            </div>
          </div>
        </article>
      </section>

      <section className="dashboard-surface-grid">
        <article className="employee-panel">
          <div className="dashboard-section-header">
            <div>
              <p className="sidebar-section-label">Meetings / Events</p>
              <h3 className="module-panel-title">Upcoming meetings & events</h3>
            </div>
          </div>

          <div className="dashboard-events-list">
            {summary.upcoming_events.length ? summary.upcoming_events.map((event) => {
              const eventDate = formatEventDate(event.date);
              return (
                <article className="dashboard-event-card" key={`${event.title}-${event.date}-${event.time}`}>
                  <div className="dashboard-event-date">
                    <span>{eventDate.month}</span>
                    <strong>{eventDate.day}</strong>
                  </div>
                  <div className="dashboard-event-body">
                    <div className="dashboard-event-meta">
                      <span className={`status-chip status-chip--${event.type}`}>{event.type}</span>
                      <span>{eventDate.weekday}</span>
                      <span>{event.time}</span>
                    </div>
                    <strong>{event.title}</strong>
                    <p>{event.subtitle}</p>
                  </div>
                </article>
              );
            }) : (
              <div className="employee-empty-state">
                <CalendarClock size={18} />
                <span>No upcoming meetings or events are scheduled right now.</span>
              </div>
            )}
          </div>
        </article>

      </section>

    </div>
  );
}

export default DashboardPage;
