export function normalizeRoleCode(value) {
  return String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
}

export function isSuperAdminUser(user) {
  return Boolean(
    user?.is_super_admin
      || normalizeRoleCode(user?.role?.code) === "super_admin"
      || String(user?.role?.name || "").trim().toLowerCase() === "super admin",
  );
}
