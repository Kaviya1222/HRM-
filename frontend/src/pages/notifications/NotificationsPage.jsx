import { useEffect, useMemo, useState } from "react";
import { Bell, CheckCheck, MailOpen, RefreshCw, ShieldCheck } from "lucide-react";
import { fetchNotifications, markNotificationRead } from "../../api/notificationApi";

function formatDateTime(value) {
  if (!value) {
    return "--";
  }
  return new Date(value).toLocaleString("en-IN");
}

function NotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const cards = useMemo(() => [
    { label: "Total Notifications", value: notifications.length },
    { label: "Unread", value: unreadCount },
    { label: "Read", value: notifications.length - unreadCount },
  ], [notifications.length, unreadCount]);

  async function loadNotifications({ silent = false } = {}) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const response = await fetchNotifications({ unread_only: unreadOnly });
      setNotifications(response.items);
      setUnreadCount(response.unread_count);
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to load notifications.",
      });
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    loadNotifications();
  }, [unreadOnly]);

  async function handleToggleRead(notification) {
    try {
      await markNotificationRead(notification.id, !notification.read_at);
      await loadNotifications({ silent: true });
    } catch (error) {
      setFeedback({
        type: "error",
        message: error.response?.data?.detail || "Unable to update notification state.",
      });
    }
  }

  if (isLoading) {
    return (
      <div className="page-container">
        <div className="settings-loading">
          <div className="settings-loading-spinner" />
          <span>Loading notifications...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-container employee-page">
      <div className="page-section-header">
        <div className="page-section-header-icon">
          <Bell size={22} />
        </div>
        <div>
          <h2 className="page-section-header-title">Notifications</h2>
          <p className="page-section-header-sub">
            Review approval alerts, payroll updates, and workflow messages targeted to the current user.
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
        {cards.map((card) => (
          <div className="employee-stat-card" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>

      <section className="employee-panel">
        <div className="module-toolbar">
          <div>
            <p className="sidebar-section-label">Inbox</p>
            <h3 className="module-panel-title">Notification center</h3>
          </div>

          <div className="employee-row-actions">
            <label className="sf-field sf-field--inline module-toggle-row">
              <input checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} type="checkbox" />
              <span className="sf-label">Unread only</span>
            </label>
            <button className="ghost-button" onClick={() => loadNotifications({ silent: true })} type="button">
              <RefreshCw size={14} className={isRefreshing ? "spin" : ""} />
              Refresh
            </button>
          </div>
        </div>

        <div className="module-list-stack">
          {notifications.map((notification) => (
            <article className={`notification-card ${notification.read_at ? "is-read" : "is-unread"}`} key={notification.id}>
              <div className="notification-card-main">
                <div className="notification-card-title-row">
                  <strong>{notification.title}</strong>
                  <span className={`status-chip status-chip--${notification.read_at ? "completed" : "pending"}`}>
                    {notification.read_at ? "Read" : "Unread"}
                  </span>
                </div>
                <p>{notification.message}</p>
                <span className="notification-card-time">{formatDateTime(notification.created_at)}</span>
              </div>
              <button className="ghost-button employee-row-btn" onClick={() => handleToggleRead(notification)} type="button">
                {notification.read_at ? <MailOpen size={14} /> : <CheckCheck size={14} />}
                {notification.read_at ? "Mark Unread" : "Mark Read"}
              </button>
            </article>
          ))}

          {!notifications.length ? (
            <div className="employee-empty-state">
              <Bell size={18} />
              <span>No notifications available for the current filter.</span>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default NotificationsPage;
