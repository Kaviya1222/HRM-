import apiClient from "./client";

export async function fetchPayrollMeta() {
  const response = await apiClient.get("/payroll/meta");
  return response.data;
}

export async function fetchPayrollSummary() {
  const response = await apiClient.get("/payroll/summary");
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

export async function fetchSalaryStructures() {
  const response = await apiClient.get("/payroll/salary-structures");
  return response.data;
}

export async function saveSalaryStructure(payload) {
  const response = await apiClient.post("/payroll/salary-structures", payload);
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

export async function downloadPayslip(payslipId) {
  const response = await apiClient.get(`/payroll/payslips/${payslipId}/download`, {
    responseType: "text",
  });
  return response.data;
}
