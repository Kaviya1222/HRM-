import apiClient from "./client";

export async function fetchEmployees(params = {}) {
  const response = await apiClient.get("/employees", { params });
  return response.data;
}

export async function fetchEmployeeMeta() {
  const response = await apiClient.get("/employees/meta");
  return response.data;
}

export async function fetchEmployeeDetail(employeeId) {
  const response = await apiClient.get(`/employees/${employeeId}`);
  return response.data;
}

export async function createEmployee(payload) {
  const response = await apiClient.post("/employees", payload);
  return response.data;
}

export async function updateEmployee(employeeId, payload) {
  const response = await apiClient.put(`/employees/${employeeId}`, payload);
  return response.data;
}

export async function updateEmployeeStatus(employeeId, isActive) {
  const response = await apiClient.patch(`/employees/${employeeId}/status`, {
    is_active: isActive,
  });
  return response.data;
}

export async function deleteEmployee(employeeId) {
  const response = await apiClient.delete(`/employees/${employeeId}`);
  return response.data;
}
