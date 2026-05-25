import axios from "axios";
import { clearSessionTokens, getAccessToken, getRefreshToken, setSessionTokens } from "../utils/tokenStorage";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

let refreshPromise = null;

apiClient.interceptors.request.use((config) => {
  const accessToken = getAccessToken();

  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const refreshToken = getRefreshToken();
    const isUnauthorized = error.response?.status === 401;
    const isRefreshRequest = originalRequest?.url?.includes("/auth/refresh");

    if (!isUnauthorized || !refreshToken || originalRequest?._retry || isRefreshRequest) {
      if (isRefreshRequest) {
        clearSessionTokens();
      }
      throw error;
    }

    originalRequest._retry = true;

    if (!refreshPromise) {
      refreshPromise = axios
        .post(`${API_BASE_URL}/auth/refresh`, {
          refresh_token: refreshToken,
        })
        .then((response) => {
          setSessionTokens(response.data);
          return response.data;
        })
        .catch((refreshError) => {
          clearSessionTokens();
          window.location.href = "/login";
          throw refreshError;
        })
        .finally(() => {
          refreshPromise = null;
        });
    }

    await refreshPromise;
    originalRequest.headers.Authorization = `Bearer ${getAccessToken()}`;
    return apiClient(originalRequest);
  },
);

export { API_BASE_URL };
export default apiClient;
