import apiClient from "./client";

export async function fetchRoles() {
  const response = await apiClient.get("/settings/roles");
  return response.data;
}

export async function fetchPermissionCatalog() {
  const response = await apiClient.get("/settings/permissions/catalog");
  return response.data;
}

export async function fetchRolePermissions(roleId) {
  const response = await apiClient.get(`/settings/roles/${roleId}/permissions`);
  return response.data;
}

export async function saveRolePermissions(roleId, assignments) {
  const response = await apiClient.put(`/settings/roles/${roleId}/permissions`, {
    assignments,
  });
  return response.data;
}

export async function fetchAppSettings() {
  const response = await apiClient.get("/settings/app-settings");
  return response.data;
}

export async function fetchPublicBranding() {
  const response = await apiClient.get("/settings/branding");
  return response.data;
}

export async function saveAppSettings(items) {
  const response = await apiClient.put("/settings/app-settings", {
    items,
  });
  return response.data;
}

export async function uploadBrandingLogo(file) {
  const formData = new FormData();
  formData.append("logo", file);
  const response = await apiClient.post("/settings/branding/logo", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return response.data;
}
