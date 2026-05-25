import apiClient from "./client";

export async function fetchNotifications(params = {}) {
  const response = await apiClient.get("/notifications", { params });
  return response.data;
}

export async function markNotificationRead(notificationId, isRead = true) {
  const response = await apiClient.patch(`/notifications/${notificationId}/read`, {
    is_read: isRead,
  });
  return response.data;
}
