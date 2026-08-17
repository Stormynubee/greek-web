import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getMe } from "@/lib/api";

const AuthCtx = createContext(null);

async function getAdminMe() {
  try {
    const r = await api.get("/admin/me");
    return r.data;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [u, a] = await Promise.all([getMe(), getAdminMe()]);
    setUser(u); setAdmin(a);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loginDiscord = useCallback(async () => {
    const r = await api.get("/auth/discord/login");
    window.location.href = r.data.url;
  }, []);

  const logout = useCallback(async () => {
    await api.post("/auth/logout");
    setUser(null);
  }, []);

  const adminLogout = useCallback(async () => {
    await api.post("/admin/logout");
    setAdmin(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, admin, loading, refresh, loginDiscord, logout, adminLogout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
