import axios from "axios";

const configuredBackendUrl = (process.env.REACT_APP_BACKEND_URL || "")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/api$/, "");
export const API_CONFIG_ERROR = configuredBackendUrl
  ? null
  : "The API URL is not configured. Set REACT_APP_BACKEND_URL before building the frontend.";
export const BACKEND_URL = configuredBackendUrl;
export const API_BASE = configuredBackendUrl ? `${BACKEND_URL}/api` : "/api";
const AUTH_TOKEN_KEY = "ggb_access_token";

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  timeout: 10000,
});

export function storeAuthToken(token) {
  if (typeof window === "undefined") return;
  if (token) window.sessionStorage.setItem(AUTH_TOKEN_KEY, token);
  else window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined" && !config.headers?.Authorization) {
    const token = window.sessionStorage.getItem(AUTH_TOKEN_KEY);
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export async function getMe() {
  try {
    const r = await api.get("/auth/me");
    return r.data;
  } catch (error) {
    if (error?.response?.status === 401) return null;
    throw error;
  }
}

export function describeApiError(error, fallback = "The API is unavailable right now.") {
  if (API_CONFIG_ERROR) return API_CONFIG_ERROR;
  if (error?.response?.data?.detail) return error.response.data.detail;
  if (error?.code === "ECONNABORTED") return "The API request timed out. Try again.";
  if (!error?.response) return "Could not reach the API. Check that the backend is running.";
  return fallback;
}
