import apiClient from "./client";

export async function fetchAttendanceMeta() {
  const response = await apiClient.get("/attendance/meta");
  return response.data;
}

export async function fetchTodayAttendance() {
  const response = await apiClient.get("/attendance/today");
  return response.data;
}

export async function fetchTodayAttendanceStats() {
  const response = await apiClient.get("/attendance/today-stats");
  return response.data;
}

export async function fetchAttendance(params = {}) {
  const response = await apiClient.get("/attendance", { params });
  return response.data;
}

export async function updateManualAttendance(payload) {
  const response = await apiClient.post("/attendance/manual", payload);
  return response.data;
}

export async function checkIn(payload = {}) {
  const response = await apiClient.post("/attendance/check-in", payload);
  return response.data;
}

export async function checkOut(payload = {}) {
  const response = await apiClient.post("/attendance/check-out", payload);
  return response.data;
}

export async function correctAttendance(logId, payload) {
  const response = await apiClient.post(`/attendance/${logId}/corrections`, payload);
  return response.data;
}
