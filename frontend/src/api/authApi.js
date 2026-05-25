import axios from "axios";
import apiClient, { API_BASE_URL } from "./client";

export async function login(payload) {
  const response = await apiClient.post("/auth/login", payload);
  return response.data;
}

export async function logout(payload = {}) {
  const response = await apiClient.post("/auth/logout", payload);
  return response.data;
}

export async function getCurrentUser() {
  const response = await apiClient.get("/auth/me");
  return response.data;
}

export async function refreshTokens(refreshToken) {
  const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
    refresh_token: refreshToken,
  });
  return response.data;
}
