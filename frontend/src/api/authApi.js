import axios from "axios";
import apiClient, { API_BASE_URL } from "./client";
import { getAccessToken } from "../utils/tokenStorage";

const AUTH_API_BASE_URL = import.meta.env.VITE_AUTH_API_BASE_URL || API_BASE_URL;

const authClient = axios.create({
  baseURL: AUTH_API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

authClient.interceptors.request.use((config) => {
  const accessToken = getAccessToken();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

export async function login(payload) {
  const response = await authClient.post("/auth/login", payload);
  return response.data;
}

export async function logout(payload = {}) {
  const response = await authClient.post("/auth/logout", payload);
  return response.data;
}

export async function getCurrentUser() {
  const response = await authClient.get("/auth/me");
  return response.data;
}

export async function refreshTokens(refreshToken) {
  const response = await axios.post(`${AUTH_API_BASE_URL}/auth/refresh`, {
    refresh_token: refreshToken,
  });
  return response.data;
}

export async function forgotPassword(email) {
  const response = await authClient.post("/auth/forgot-password", { email });
  return response.data;
}

export async function resetPassword(payload) {
  const response = await authClient.post("/auth/reset-password", payload);
  return response.data;
}

export async function changeFirstLoginPassword(payload) {
  const response = await authClient.post("/auth/first-login-password", payload);
  return response.data;
}
