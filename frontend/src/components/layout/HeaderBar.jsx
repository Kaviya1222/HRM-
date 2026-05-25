import { useLocation, useNavigate } from "react-router-dom";
import { Bell, Search, LogOut, ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { fetchNotifications, markNotificationRead } from "../../api/notificationApi";
import { globalSearch } from "../../api/searchApi";
import useAuth from "../../hooks/useAuth";
import useBranding from "../../hooks/useBranding";

const PAGE_TITLES = {
  "/": "Dashboard",
  "/employees": "Employee Management",
  "/attendance": "Attendance",
  "/leave": "Leave Management",
  "/payroll": "Payroll",
  "/reports": "Report",
  "/calendar": "Calendar",
  "/notifications": "Notifications",
  "/tracker": "Tracker Monitoring",
  "/settings": "System Settings",
};

function HeaderBar() {
  const { user, logout, hasPermission } = useAuth();
  const { branding } = useBranding();
  const location = useLocation();
  const navigate = useNavigate();
  const notificationMenuRef = useRef(null);
  const searchMenuRef = useRef(null);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showNotifications, setShowNotifications] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [notificationsError, setNotificationsError] = useState("");
  const [isNotificationsLoading, setIsNotificationsLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showSearchPanel, setShowSearchPanel] = useState(false);
  const [searchResults, setSearchResults] = useState({ query: "", total_results: 0, sections: [] });
  const [searchError, setSearchError] = useState("");
  const [isSearchLoading, setIsSearchLoading] = useState(false);
  const canViewNotifications = hasPermission("notifications.view.own") || hasPermission("notifications.manage");

  const pageTitle = Object.entries(PAGE_TITLES).find(([path]) =>
    path === "/" ? location.pathname === "/" : location.pathname.startsWith(path)
  )?.[1] ?? branding.organizationName;

  useEffect(() => {
    document.title = `${pageTitle} | ${branding.organizationName}`;
  }, [branding.organizationName, pageTitle]);

  useEffect(() => {
    if (!canViewNotifications) {
      setUnreadCount(0);
      return;
    }

    let isMounted = true;

    async function loadUnreadCount() {
      try {
        const response = await fetchNotifications({ unread_only: true });
        if (isMounted) {
          setUnreadCount(response.unread_count || response.items.length || 0);
        }
      } catch (_error) {
        if (isMounted) {
          setUnreadCount(0);
        }
      }
    }

    loadUnreadCount();
    const intervalId = window.setInterval(loadUnreadCount, 30000);
    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, [canViewNotifications, user?.id]);

  useEffect(() => {
    if (!showNotifications) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (notificationMenuRef.current && !notificationMenuRef.current.contains(event.target)) {
        setShowNotifications(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setShowNotifications(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showNotifications]);

  useEffect(() => {
    const normalizedQuery = searchQuery.trim();

    if (normalizedQuery.length < 2) {
      setIsSearchLoading(false);
      setSearchError("");
      setSearchResults({ query: normalizedQuery, total_results: 0, sections: [] });
      return undefined;
    }

    let isMounted = true;
    const timeoutId = window.setTimeout(async () => {
      setIsSearchLoading(true);
      setSearchError("");

      try {
        const response = await globalSearch(normalizedQuery);
        if (isMounted) {
          setSearchResults(response);
          setShowSearchPanel(true);
        }
      } catch (_error) {
        if (isMounted) {
          setSearchResults({ query: normalizedQuery, total_results: 0, sections: [] });
          setSearchError("Unable to search right now.");
        }
      } finally {
        if (isMounted) {
          setIsSearchLoading(false);
        }
      }
    }, 220);

    return () => {
      isMounted = false;
      window.clearTimeout(timeoutId);
    };
  }, [searchQuery]);

  useEffect(() => {
    if (!showSearchPanel) {
      return undefined;
    }

    function handlePointerDown(event) {
      if (searchMenuRef.current && !searchMenuRef.current.contains(event.target)) {
        setShowSearchPanel(false);
      }
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setShowSearchPanel(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showSearchPanel]);

  async function loadNotificationPreview() {
    if (!canViewNotifications) {
      setNotifications([]);
      setNotificationsError("");
      return;
    }

    setIsNotificationsLoading(true);
    setNotificationsError("");
    try {
      const response = await fetchNotifications();
      setNotifications(response.items || []);
      setUnreadCount(response.unread_count || response.items?.filter((item) => !item.read_at).length || 0);
    } catch (_error) {
      setNotifications([]);
      setNotificationsError("Unable to load notifications.");
    } finally {
      setIsNotificationsLoading(false);
    }
  }

  async function handleNotificationClick() {
    const nextOpen = !showNotifications;
    setShowNotifications(nextOpen);

    if (nextOpen) {
      await loadNotificationPreview();
    }
  }

  function getNotificationTargetUrl(notification) {
    const explicitTarget = notification?.target_url || notification?.metadata_json?.target_url;
    if (explicitTarget) {
      return explicitTarget;
    }

    const notificationType = String(notification?.notification_type || "").toLowerCase();
    const title = String(notification?.title || "").toLowerCase();
    const message = String(notification?.message || "").toLowerCase();
    if (
      notificationType === "leave_approved"
      || notificationType === "leave_rejected"
      || (notificationType === "approval" && (title.includes("leave") || message.includes("leave")))
    ) {
      return "/leave";
    }
    if (notificationType === "calendar" || title.includes("meeting") || title.includes("huddle")) {
      return "/calendar";
    }
    if (notificationType === "payroll" || title.includes("payroll") || title.includes("payslip")) {
      return "/payroll";
    }
    return "";
  }

  async function handleNotificationItemClick(notification) {
    if (!notification?.id) {
      return;
    }

    const targetUrl = getNotificationTargetUrl(notification);
    try {
      if (!notification.read_at) {
        await markNotificationRead(notification.id, true);
        setNotifications((current) => current.map((item) => (
          item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item
        )));
        setUnreadCount((current) => Math.max(current - 1, 0));
      }
    } catch (_error) {
      setNotificationsError("Unable to update notification status.");
    }

    if (targetUrl) {
      setShowNotifications(false);
      navigate(targetUrl);
    }
  }

  function formatNotificationTime(value) {
    if (!value) {
      return "";
    }

    return new Date(value).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function handleSearchChange(event) {
    const nextValue = event.target.value;
    setSearchQuery(nextValue);
    setShowSearchPanel(Boolean(nextValue.trim()));
  }

  function handleSearchFocus() {
    if (searchQuery.trim()) {
      setShowSearchPanel(true);
    }
  }

  function handleSearchSelect(path) {
    setShowSearchPanel(false);
    setSearchQuery("");
    setSearchResults({ query: "", total_results: 0, sections: [] });
    setSearchError("");
    navigate(path);
  }

  function handleSearchKeyDown(event) {
    if (event.key !== "Enter") {
      return;
    }

    const firstResult = searchResults.sections[0]?.items?.[0];
    if (!firstResult) {
      return;
    }

    event.preventDefault();
    handleSearchSelect(firstResult.path);
  }

  return (
    <header className="topbar">
      <div className="topbar-left">
        <h1 className="topbar-page-title">{pageTitle}</h1>
      </div>

      <div className="topbar-right">
        {/* Search */}
        <div className="topbar-search" ref={searchMenuRef}>
          <Search size={15} className="topbar-search-icon" />
          <input
            className="topbar-search-input"
            placeholder="Search..."
            type="text"
            value={searchQuery}
            onChange={handleSearchChange}
            onFocus={handleSearchFocus}
            onKeyDown={handleSearchKeyDown}
          />

          {showSearchPanel ? (
            <div className="topbar-search-panel">
              {searchQuery.trim().length < 2 ? (
                <div className="topbar-search-empty">Type at least 2 characters to search.</div>
              ) : isSearchLoading ? (
                <div className="topbar-search-empty">Searching across modules...</div>
              ) : searchError ? (
                <div className="topbar-search-empty">{searchError}</div>
              ) : searchResults.sections.length ? (
                <div className="topbar-search-results">
                  {searchResults.sections.map((section) => (
                    <section className="topbar-search-section" key={section.module}>
                      <div className="topbar-search-section-header">
                        <strong>{section.label}</strong>
                        <span>{section.items.length}</span>
                      </div>

                      <div className="topbar-search-section-items">
                        {section.items.map((item) => (
                          <button
                            key={`${item.module}-${item.id}`}
                            className="topbar-search-result"
                            onClick={() => handleSearchSelect(item.path)}
                            type="button"
                          >
                            <strong>{item.title}</strong>
                            <span>{item.subtitle}</span>
                            {item.description ? <p>{item.description}</p> : null}
                          </button>
                        ))}
                      </div>
                    </section>
                  ))}
                </div>
              ) : (
                <div className="topbar-search-empty">No results found for "{searchQuery.trim()}".</div>
              )}
            </div>
          ) : null}
        </div>

        {/* Notifications */}
        <div className="topbar-notifications" ref={notificationMenuRef}>
          <button
            className="topbar-icon-btn"
            type="button"
            aria-label="Notifications"
            aria-expanded={showNotifications}
            onClick={handleNotificationClick}
          >
            <Bell size={18} />
            {unreadCount ? <span className="topbar-badge">{Math.min(unreadCount, 9)}</span> : null}
          </button>

          {showNotifications ? (
            <div className="topbar-notification-popup">
              <div className="topbar-notification-header">
                <strong>Notifications</strong>
                {unreadCount ? <span className="topbar-notification-count">{unreadCount} unread</span> : null}
              </div>

              <div className="topbar-notification-list">
                {isNotificationsLoading ? (
                  <div className="topbar-notification-empty">Loading notifications...</div>
                ) : notificationsError ? (
                  <div className="topbar-notification-empty">{notificationsError}</div>
                ) : notifications.length ? (
                  notifications.slice(0, 5).map((notification) => (
                    <article
                      key={notification.id}
                      className={`topbar-notification-item ${notification.read_at ? "is-read" : "is-unread"}`}
                      onClick={() => handleNotificationItemClick(notification)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleNotificationItemClick(notification);
                        }
                      }}
                    >
                      <div className="topbar-notification-item-head">
                        <strong>{notification.title}</strong>
                        {!notification.read_at ? <span className="topbar-notification-dot" /> : null}
                      </div>
                      <p>{notification.message}</p>
                      <span>{formatNotificationTime(notification.created_at)}</span>
                    </article>
                  ))
                ) : (
                  <div className="topbar-notification-empty">No notifications available.</div>
                )}
              </div>
            </div>
          ) : null}
        </div>

        {/* User menu */}
        <div className="topbar-user" onClick={() => setShowUserMenu((v) => !v)}>
          <div className="topbar-avatar">
            {user?.first_name?.[0]}{user?.last_name?.[0]}
          </div>
          <div className="topbar-user-info">
            <span className="topbar-user-name">{user?.full_name}</span>
            <span className="topbar-user-role">{user?.role?.name}</span>
          </div>
          <ChevronDown size={14} className={`topbar-chevron ${showUserMenu ? "open" : ""}`} />

          {showUserMenu && (
            <div className="topbar-dropdown">
              <div className="topbar-dropdown-header">
                <strong>{user?.full_name}</strong>
                <span>{user?.email}</span>
              </div>
              <hr className="topbar-dropdown-divider" />
              <button
                className="topbar-dropdown-item topbar-dropdown-item--danger"
                onClick={(e) => { e.stopPropagation(); logout(); }}
                type="button"
              >
                <LogOut size={15} />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default HeaderBar;
