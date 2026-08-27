import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Admin access is now Discord-role based (no username/password). This page:
 *  - signs the user in via their single Discord login if they are not signed in
 *  - lets an admin/owner through to /admin
 *  - shows a clear "no access" state for non-admins
 */
export default function AdminLoginPage() {
  const { user, admin, loading, loginDiscord, authError } = useAuth();
  const nav = useNavigate();

  const canAccess = user?.role === "admin" || user?.role === "owner";

  useEffect(() => {
    if (loading) return;
    if (canAccess) {
      nav("/admin", { replace: true });
    } else if (!user) {
      loginDiscord();
    }
  }, [loading, canAccess, user, loginDiscord, nav]);

  return (
    <section className="min-h-screen bg-[#0a0a0a] text-[#efe9dc] flex items-center justify-center px-4">
      <div className="code-sequence brutal-border-ivory bg-black brutal-shadow-red w-full max-w-md p-6 text-center">
        <div className="chip chip-red mb-3">SHOGUN&apos;S GATE</div>
        <h1 className="font-anton uppercase text-4xl leading-none tracking-tight">Admin Console</h1>
        {loading ? (
          <p className="font-mono text-xs opacity-70 mt-6">Checking your access…</p>
        ) : canAccess ? (
          <p className="font-mono text-xs opacity-80 mt-6">Redirecting to the console…</p>
        ) : (
          <div className="mt-6">
            <p className="font-mono text-xs opacity-70">
              {user
                ? "This Discord account is not on the admin allowlist."
                : "Sign in with Discord to check access."}
            </p>
            {!user && (
              <button
                onClick={loginDiscord}
                className="mt-6 w-full font-anton uppercase text-xl py-3 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover">
                Log in with Discord
              </button>
            )}
            {authError && (
              <p className="mt-4 brutal-border p-2 bg-[#da291c] text-[#efe9dc] font-mono text-xs">{authError}</p>
            )}
          </div>
        )}
        <button
          onClick={() => nav("/", { replace: true })}
          className="mt-6 w-full font-anton uppercase text-sm py-2 brutal-border brutal-hover opacity-80">
          ← Back to the stream
        </button>
      </div>
    </section>
  );
}