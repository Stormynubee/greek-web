import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { api, API_CONFIG_ERROR, describeApiError, getMe, storeAuthToken } from "@/lib/api";

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
  const refreshSequence = useRef(0);
  const loginInFlight = useRef(false);
  const completedHandoff = useRef(null);

  const refresh = useCallback(async () => {
    const sequence = refreshSequence.current + 1;
    refreshSequence.current = sequence;
    if (API_CONFIG_ERROR) {
      setBootstrapError(API_CONFIG_ERROR);
      setLoading(false);
      return;
    }
    const [u, a] = await Promise.allSettled([getMe(), getAdminMe()]);
    if (sequence !== refreshSequence.current) return;
    setUser(u.status === "fulfilled" ? u.value : null);
    setAdmin(a.status === "fulfilled" ? a.value : null);
    const failed = [u, a].find((result) => result.status === "rejected");
    setBootstrapError(failed ? describeApiError(failed.reason, "Could not restore your session.") : null);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ticket = params.get("auth_ticket");
    if (!ticket) return;
    if (completedHandoff.current === ticket) return;
    completedHandoff.current = ticket;

    params.delete("auth_ticket");
    const cleanQuery = params.toString();
    window.history.replaceState(
      {},
      document.title,
      `${window.location.pathname}${cleanQuery ? `?${cleanQuery}` : ""}${window.location.hash}`,
    );

    api.post("/auth/discord/complete", { ticket })
      .then((response) => {
        storeAuthToken(response.data?.token);
        setAuthError(null);
        return refresh();
      })
      .catch(async (error) => {
        // A duplicate callback can race the successful one-time handoff. If
        // the session is already authenticated, do not replace the success
        // state with a stale-ticket error.
        if (error?.response?.status === 401) {
          try {
            if (await getMe()) return;
          } catch {
            // Fall through to the user-facing error below.
          }
        }
        setAuthError(describeApiError(error, "Your Discord login handoff expired. Please try again."));
      });
  }, [refresh]);

  const loginDiscord = useCallback(async () => {
    if (loginInFlight.current) return;
    setAuthError(null);
    loginInFlight.current = true;
    try {
      const r = await api.get("/auth/discord/login");
      const authorizeUrl = r.data?.url;
      const parsed = new URL(authorizeUrl);
      if (parsed.origin !== "https://discord.com" || !parsed.pathname.startsWith("/api/oauth2/authorize")) {
        throw new Error("The API returned an invalid Discord login URL.");
      }
      window.location.assign(parsed.toString());
    } catch (error) {
      loginInFlight.current = false;
      setAuthError(describeApiError(error, "Discord login is unavailable right now."));
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
      setAuthError(null);
    } catch (error) {
      setAuthError(describeApiError(error, "Could not contact the API, so you were signed out locally."));
    } finally {
      storeAuthToken(null);
      setUser(null);
    }
  }, []);

  const adminLogout = useCallback(async () => {
    try {
      await api.post("/admin/logout");
      setAuthError(null);
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
