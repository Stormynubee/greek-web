import axios from "axios";
import { getSupabaseAccessToken } from "@/lib/supabase";

const configuredBackendUrl = (process.env.REACT_APP_BACKEND_URL || "")
  .trim()
  .replace(/\/+$/, "")
  .replace(/\/api$/, "");
export const API_CONFIG_ERROR = configuredBackendUrl
  ? null
  : "The API URL is not configured. Set REACT_APP_BACKEND_URL before building the frontend.";
export const BACKEND_URL = configuredBackendUrl;
export const API_BASE = configuredBackendUrl ? `${BACKEND_URL}/api` : "/api";

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  timeout: 10000,
});

// Use the Supabase session as the single Bearer token for the site API.
// The backend resolves the Supabase JWT to a user (Phase 4 contract).
export async function getMe() {
  try {
    const token = await getSupabaseAccessToken();
    const r = await api.get("/auth/me", ...(token ? [{ headers: { Authorization: `Bearer ${token}` } }] : []));
    return r.data;
  } catch (error) {
    if (error?.response?.status === 401) return null;
    throw error;
  }
}

api.interceptors.request.use(
  async (config) => {
    if (!config.headers?.Authorization) {
      const token = await getSupabaseAccessToken();
      if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error),
);

export function describeApiError(error, fallback = "The API is unavailable right now.") {
  if (API_CONFIG_ERROR) return API_CONFIG_ERROR;
  if (error?.response?.data?.detail) return error.response.data.detail;
  if (error?.code === "ECONNABORTED") return "The API request timed out. Try again.";
  if (!error?.response) return "Could not reach the API. Check that the backend is running.";
  return fallback;
}