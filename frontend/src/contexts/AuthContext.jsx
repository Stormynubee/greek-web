import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, getMe } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const u = await getMe();
    setUser(u);
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

  return (
    <AuthCtx.Provider value={{ user, loading, refresh, loginDiscord, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
