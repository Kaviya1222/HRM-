import apiClient from "./client";

export async function fetchMonthlyAttendanceReport(month, year) {
  const response = await apiClient.get("/reports/monthly-attendance", {
    params: { month, year },
  });
  return response.data;
}

export async function fetchEmployeeSubmittedReports() {
  const response = await apiClient.get("/reports/submitted");
  return response.data;
}

export async function submitEmployeeReport(payload) {
  const response = await apiClient.post("/reports/submitted", payload);
  return response.data;
}

export async function fetchEmployeeSubmittedReport(reportId) {
  const response = await apiClient.get(`/reports/submitted/${reportId}`);
  return response.data;
}

export async function exportMonthlyAttendanceCsv(month, year) {
  const response = await apiClient.get("/reports/monthly-attendance/export", {
    params: { month, year },
    responseType: "blob",
  });
  return response.data;
}
