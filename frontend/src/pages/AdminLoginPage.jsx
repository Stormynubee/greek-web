import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, describeApiError } from "@/lib/api";
import { ADMIN_AUTH } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

export default function AdminLoginPage() {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const { refresh } = useAuth();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await api.post("/admin/login", { username: u, password: p });
      await refresh();
      nav("/admin", { replace: true });
    } catch (e2) {
      setErr(describeApiError(e2, "Admin login failed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      data-testid={ADMIN_AUTH.loginPage}
      className="min-h-screen bg-[#0a0a0a] text-[#efe9dc] flex items-center justify-center px-4"
    >
      <form onSubmit={submit}
        className="brutal-border-ivory bg-black brutal-shadow-red w-full max-w-md p-6">
        <div className="chip chip-red mb-3">SHOGUN&apos;S GATE</div>
        <h1 className="font-anton uppercase text-4xl leading-none tracking-tight">Admin Login</h1>
        <p className="font-mono text-xs opacity-70 mt-2">Owner-only console. Credentials are bcrypt-hashed and rate-limited.</p>

        <label className="block mt-6 font-mono text-xs uppercase">Username
          <input
            data-testid={ADMIN_AUTH.username}
            value={u} onChange={(e) => setU(e.target.value)} required autoComplete="username"
            className="mt-1 w-full brutal-border bg-[#efe9dc] text-black p-2 font-mono"
          />
        </label>
        <label className="block mt-4 font-mono text-xs uppercase">Password
          <input
            data-testid={ADMIN_AUTH.password}
            value={p} onChange={(e) => setP(e.target.value)} required type="password" autoComplete="current-password"
            className="mt-1 w-full brutal-border bg-[#efe9dc] text-black p-2 font-mono"
          />
        </label>

        {err && (
          <div data-testid={ADMIN_AUTH.error}
            className="mt-4 brutal-border p-2 bg-[#da291c] text-[#efe9dc] font-mono text-xs">{err}</div>
        )}

        <button
          data-testid={ADMIN_AUTH.submit}
          disabled={busy || !u || !p}
          className="mt-6 w-full font-anton uppercase text-xl py-3 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover disabled:opacity-50">
          {busy ? "Entering..." : "Enter the Console →"}
        </button>
      </form>
    </section>
  );
}
