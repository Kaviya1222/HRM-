import apiClient from "./client";

export async function fetchTrackerMonitor() {
  const response = await apiClient.get("/tracker/monitor");
  return response.data;
}

export async function fetchTrackerLiveStatus() {
  const response = await apiClient.get("/tracker/live-status");
  return response.data;
}

export async function trackerCheckIn(payload = {}) {
  const response = await apiClient.post("/tracker/checkin", payload);
  return response.data;
}

export async function sendTrackerHeartbeat(payload = {}) {
  const response = await apiClient.post("/tracker/heartbeat", payload);
  return response.data;
}

export async function trackerLogout(payload = {}) {
  const response = await apiClient.post("/tracker/logout", payload);
  return response.data;
}

export async function updateTrackerStatus(payload) {
  const response = await apiClient.post("/tracker/status", payload);
  return response.data;
}
