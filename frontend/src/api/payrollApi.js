import apiClient from "./client";

export async function fetchPayrollMeta() {
  const response = await apiClient.get("/payroll/meta");
  return response.data;
}

export async function fetchPayrollSummary() {
  const response = await apiClient.get("/payroll/summary");
  return response.data;
}

export async function fetchPayrollDashboardSummary(params = {}) {
  const response = await apiClient.get("/payroll/dashboard-summary", { params });
  return response.data;
}

export async function fetchPayrollTransactions() {
  const response = await apiClient.get("/payroll/transactions");
  return response.data;
}

export async function addPayrollTransaction(payload) {
  const response = await apiClient.post("/payroll/transactions", payload);
  return response.data;
}

export async function updatePayrollTransaction(transactionId, payload) {
  const response = await apiClient.put(`/payroll/transactions/${transactionId}`, payload);
  return response.data;
}

export async function deletePayrollTransaction(transactionId) {
  const response = await apiClient.delete(`/payroll/transactions/${transactionId}`);
  return response.data;
}

export async function fetchSalaryStructures() {
  const response = await apiClient.get("/payroll/salary-structures");
  return response.data;
}

export async function saveSalaryStructure(payload) {
  const response = await apiClient.post("/payroll/salary-structures", payload);
  return response.data;
}

export async function fetchSalaryProfile(employeeId) {
  const response = await apiClient.get(`/payroll/salary-profiles/${employeeId}`);
  return response.data;
}

export async function fetchSalaryProfiles() {
  const response = await apiClient.get("/payroll/salary-profiles");
  return response.data;
}

export async function saveSalaryProfile(payload) {
  const response = await apiClient.post("/payroll/salary-profiles", payload);
  return response.data;
}

export async function updateSalaryProfile(employeeId, payload) {
  const response = await apiClient.put(`/payroll/salary-profiles/${employeeId}`, payload);
  return response.data;
}

export async function fetchPayrollAttendanceSummary(params) {
  const response = await apiClient.get("/payroll/attendance-summary", { params });
  return response.data;
}

export async function fetchPayrollRuns() {
  const response = await apiClient.get("/payroll/runs");
  return response.data;
}

export async function runPayroll(payload) {
  const response = await apiClient.post("/payroll/run", payload);
  return response.data;
}

export async function fetchPayslips(params = {}) {
  const response = await apiClient.get("/payroll/payslips", { params });
  return response.data;
}

export async function calculatePayslip(payload) {
  const response = await apiClient.post("/payroll/payslips/calculate", payload);
  return response.data;
}

export async function downloadPayslip(payslipId) {
  const response = await apiClient.get(`/payroll/payslips/${payslipId}/download`, {
    responseType: "text",
  });
  return response.data;
}
