import apiClient from "./client";

export async function fetchDashboardSummary() {
  const response = await apiClient.get("/dashboard/summary");
  return response.data;
}
