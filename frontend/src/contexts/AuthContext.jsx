import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { describeApiError, getMe } from "@/lib/api";
import { supabase, SUPABASE_CONFIGURED } from "@/lib/supabase";

const AuthCtx = createContext(null);

async function fetchProfile(userId) {
  // Best-effort: role + identity come from the public.profiles table.
  try {
    const { data, error } = await supabase
      .from("profiles")
      .select("discord_id, username, avatar_url, role, points_balance")
      .eq("user_id", userId)
      .maybeSingle();
    if (error || !data) return null;
    return data;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [admin, setAdmin] = useState(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState(null);
  const [authError, setAuthError] = useState(null);
  const loginInFlight = useRef(false);

  // Single source of truth: the Supabase Auth session.
  const syncFromSupabase = useCallback(async (session) => {
    if (!session?.user) {
      setUser(null);
      setAdmin(null);
      setLoading(false);
      return;
    }
    const su = session.user;

    // The site API (FastAPI) validates this same Supabase token and returns the
    // canonical user record — including the live points balance. Prefer it; fall
    // back to the Supabase profile row if the API is unreachable.
    let u = null;
    try {
      u = await getMe();
    } catch {
      u = null;
    }
    if (!u) {
      const profile = await fetchProfile(su.id);
      u = {
        id: su.id,
        discord_id: profile?.discord_id || su.user_metadata?.discord_id || null,
        username:
          profile?.username ||
          su.user_metadata?.full_name ||
          su.user_metadata?.name ||
          "user",
        avatar_url: profile?.avatar_url || su.user_metadata?.avatar_url || null,
        role: profile?.role || "viewer",
        points_balance: profile?.points_balance ?? 0,
        email: su.email || null,
      };
    }
    const isAdmin = u.role === "admin" || u.role === "owner";
    setUser(u);
    setAdmin(isAdmin ? { username: u.username, kind: "admin" } : null);
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!SUPABASE_CONFIGURED) {
      setBootstrapError(
        "Supabase Auth is not configured. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY before building.",
      );
      setLoading(false);
      return undefined;
    }
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (mounted) syncFromSupabase(data.session);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((event, session) => {
      if (!mounted) return;
      syncFromSupabase(session);
      // After the first successful SIGNED_IN, do a hard reload to a clean URL.
      // The Supabase library persists the session asynchronously; doing the
      // replaceState in the same tick can race the persistence, and the
      // user lands on `/` looking logged-out. A short delay + reload is the
      // simplest, most reliable way to get a logged-in landing.
      if (event === "SIGNED_IN" && window.location.hash.includes("access_token")) {
        // Use replaceState immediately so the URL looks clean, then reload
        // to guarantee localStorage was persisted before any component reads it.
        try {
          window.history.replaceState(
            null,
            document.title,
            window.location.pathname + window.location.search,
          );
        } catch {
          /* noop */
        }
        setTimeout(() => {
          window.location.replace(window.location.pathname + window.location.search);
        }, 150);
      }
    });
    return () => {
      mounted = false;
      sub?.subscription?.unsubscribe?.();
    };
  }, [syncFromSupabase]);

  const loginDiscord = useCallback(async () => {
    if (loginInFlight.current) return;
    setAuthError(null);
    loginInFlight.current = true;
    try {
      if (!SUPABASE_CONFIGURED || !supabase) {
        throw new Error("Supabase Auth is not configured.");
      }
      // Hard reload after Supabase writes the hash tokens to localStorage.
      // Without this, `onAuthStateChange` can fire before the session is
      // persisted, and the page may render logged-out. The reload is cheap
      // because the user just came from Discord and expects a fresh state.
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "discord",
        options: { redirectTo: window.location.origin + "/" },
      });
      if (error) throw error;
    } catch (error) {
      loginInFlight.current = false;
      setAuthError(describeApiError(error, "Discord login is unavailable right now."));
    }
  }, []);

  const refresh = useCallback(async () => {
    if (!SUPABASE_CONFIGURED) return;
    const { data } = await supabase.auth.getSession();
    await syncFromSupabase(data.session);
  }, [syncFromSupabase]);

  const logout = useCallback(async () => {
    try {
      await supabase.auth.signOut();
    } catch {
      setAuthError(describeApiError(null, "Could not sign out fully; cleared session locally."));
    } finally {
      setUser(null);
      setAdmin(null);
    }
  }, []);

  // Deprecated: there is no separate admin password session anymore.
  const adminLogout = useCallback(async () => {
    setAdmin(null);
  }, []);

  return (
    <AuthCtx.Provider
      value={{
        user,
        admin,
        loading,
        bootstrapError,
        authError,
        clearAuthError: () => setAuthError(null),
        loginDiscord,
        logout,
        adminLogout,
        refresh,
      }}
    >
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  return useContext(AuthCtx);
}