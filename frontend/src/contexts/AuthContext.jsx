import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, API_CONFIG_ERROR, describeApiError, getMe } from "@/lib/api";

const AuthCtx = createContext(null);

async function getAdminMe() {
  try {
    const r = await api.get("/admin/me");
    return r.data;
  } catch (error) {
    if (error?.response?.status === 401) return null;
    throw error;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState(null);
  const [authError, setAuthError] = useState(null);

  const refresh = useCallback(async () => {
    if (API_CONFIG_ERROR) {
      setBootstrapError(API_CONFIG_ERROR);
      setLoading(false);
      return;
    }
    const [u, a] = await Promise.allSettled([getMe(), getAdminMe()]);
    setUser(u.status === "fulfilled" ? u.value : null);
    setAdmin(a.status === "fulfilled" ? a.value : null);
    const failed = [u, a].find((result) => result.status === "rejected");
    setBootstrapError(failed ? describeApiError(failed.reason, "Could not restore your session.") : null);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const loginDiscord = useCallback(async () => {
    setAuthError(null);
    try {
      const r = await api.get("/auth/discord/login");
      window.location.href = r.data.url;
    } catch (error) {
      setAuthError(describeApiError(error, "Discord login is unavailable right now."));
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch (error) {
      setAuthError(describeApiError(error, "Could not contact the API, so you were signed out locally."));
    } finally {
      setUser(null);
    }
  }, []);

  const adminLogout = useCallback(async () => {
    try {
      await api.post("/admin/logout");
    } catch (error) {
      setAuthError(describeApiError(error, "Could not contact the API, so you were signed out locally."));
    } finally {
      setAdmin(null);
    }
  }, []);

  return (
    <AuthCtx.Provider value={{
      user,
      admin,
      loading,
      bootstrapError,
      authError,
      clearAuthError: () => setAuthError(null),
      refresh,
      loginDiscord,
      logout,
      adminLogout,
    }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() { return useContext(AuthCtx); }
