export function getRedirectPath(role) {
  const normalizedRole = String(role || "").toLowerCase();
  if (normalizedRole.includes("admin")) {
    return "/admin-dashboard";
  }
  if (normalizedRole === "hr" || normalizedRole.includes("human")) {
    return "/hr-dashboard";
  }
  return "/employee-dashboard";
}

export function getRolePermissions(role) {
  const normalizedRole = String(role || "").toLowerCase();
  if (normalizedRole.includes("admin")) {
    return ["*"];
  }
  if (normalizedRole === "hr" || normalizedRole.includes("human")) {
    return [
      "module.dashboard.access",
      "page.dashboard.view",
      "module.employees.access",
      "page.employees.view",
      "module.attendance.access",
      "page.attendance.view",
      "module.leave.access",
      "page.leave.view",
      "module.reports.access",
      "page.reports.view",
    ];
  }
  return ["module.dashboard.access", "page.dashboard.view", "module.leave.access", "page.leave.view"];
}
