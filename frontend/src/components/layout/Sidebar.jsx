import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, CalendarCheck, CalendarOff,
  CalendarDays, Banknote, BarChart3, Bell, Monitor, Settings,
  ChevronRight,
} from "lucide-react";
import useAuth from "../../hooks/useAuth";
import useBranding from "../../hooks/useBranding";
import { navigationItems } from "../../permissions/navigation";
import { isSuperAdminUser } from "../../permissions/roles";

const ICON_MAP = {
  LayoutDashboard, Users, CalendarCheck, CalendarOff,
  CalendarDays, Banknote, BarChart3, Bell, Monitor, Settings,
};

function Sidebar() {
  const { user, hasPermission } = useAuth();
  const { branding } = useBranding();
  const location = useLocation();

  const visibleItems = navigationItems.filter((item) => {
    if (item.superAdminOnly) return isSuperAdminUser(user);
    return hasPermission(item.permission);
  });

  const mainItems = visibleItems.filter((i) => i.path !== "/settings");
  const settingsItem = visibleItems.find((i) => i.path === "/settings");

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-logo">
          {branding.logoDataUrl ? (
            <img
              className="sidebar-logo-image"
              src={branding.logoDataUrl}
              alt={`${branding.organizationName} logo`}
            />
          ) : (
            <span className="sidebar-logo-text">{branding.logoText}</span>
          )}
        </div>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">{branding.organizationName}</span>
          <span className="sidebar-brand-sub">{branding.tagline}</span>
        </div>
      </div>

      {/* Nav section label */}
      <p className="sidebar-section-label">Main Menu</p>

      {/* Nav items */}
      <nav className="sidebar-nav">
        {mainItems.map((item) => {
          const Icon = ICON_MAP[item.icon] || LayoutDashboard;
          const isActive = item.path === "/"
            ? location.pathname === "/"
            : location.pathname.startsWith(item.path);
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={`sidebar-nav-item ${isActive ? "active" : ""}`}
              end={item.path === "/"}
            >
              <span className="sidebar-nav-icon">
                <Icon size={18} />
              </span>
              <span className="sidebar-nav-label">{item.label}</span>
              {isActive && <ChevronRight size={14} className="sidebar-nav-chevron" />}
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-spacer" />

      {/* Settings at bottom */}
      {settingsItem && (() => {
        const Icon = Settings;
        const isActive = location.pathname.startsWith("/settings");
        return (
          <NavLink
            to={settingsItem.path}
            className={`sidebar-nav-item sidebar-nav-item--settings ${isActive ? "active" : ""}`}
          >
            <span className="sidebar-nav-icon"><Icon size={18} /></span>
            <span className="sidebar-nav-label">{settingsItem.label}</span>
          </NavLink>
        );
      })()}

      {/* User mini card */}
      <div className="sidebar-user">
        <div className="sidebar-user-avatar">
          {user?.first_name?.[0]}{user?.last_name?.[0]}
        </div>
        <div className="sidebar-user-info">
          <span className="sidebar-user-name">{user?.full_name}</span>
          <span className="sidebar-user-role">{user?.role?.name}</span>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;
