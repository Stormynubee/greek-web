import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
});

export async function getMe() {
  try {
    const r = await api.get("/auth/me");
    return r.data;
  } catch {
    return null;
  }
}
