import apiClient from "./client";

export async function fetchLeaveMeta() {
  const response = await apiClient.get("/leave/meta");
  return response.data;
}

export async function fetchLeaveRequests(params = {}) {
  const response = await apiClient.get("/leave/requests", { params });
  return response.data;
}

export async function applyLeave(payload) {
  const response = await apiClient.post("/leave/requests", payload);
  return response.data;
}

export async function decideLeave(leaveRequestId, payload) {
  const response = await apiClient.post(`/leave/requests/${leaveRequestId}/decision`, payload);
  return response.data;
}
