import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ADMIN } from "@/constants/testIds";
import { Navigate } from "react-router-dom";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const [users, setUsers] = useState([]);
  const [game, setGame] = useState({ title: "", kind: "prediction", prompt: "", options: "", entry_cost: 0, reward_pool: 0 });
  const [grant, setGrant] = useState({ discord_id: "", delta: 0 });
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (user?.role === "owner") {
      api.get("/admin/users").then((r) => setUsers(r.data.users)).catch(() => {});
    }
  }, [user]);

  if (loading) return <div className="p-10 font-mono text-[#e8e4d9]">Loading...</div>;
  if (!user) return <Navigate to="/" replace />;
  if (user.role !== "owner") return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#e8e4d9] p-10">
      <h1 className="font-anton uppercase text-4xl">403 · Owner only</h1>
      <p className="font-mono mt-2 opacity-70">Signed in as {user.username} ({user.discord_id})</p>
    </div>
  );

  const createGame = async (e) => {
    e.preventDefault();
    try {
      await api.post("/admin/games", {
        title: game.title, kind: game.kind, prompt: game.prompt,
        options: game.options.split(",").map(s => s.trim()).filter(Boolean),
        entry_cost: Number(game.entry_cost) || 0,
        reward_pool: Number(game.reward_pool) || 0,
      });
      setMsg({ kind: "ok", text: "Game created" });
      setGame({ title: "", kind: "prediction", prompt: "", options: "", entry_cost: 0, reward_pool: 0 });
    } catch (e) {
      setMsg({ kind: "err", text: e?.response?.data?.detail || "Failed" });
    }
  };

  const doGrant = async (e) => {
    e.preventDefault();
    try {
      const r = await api.post("/admin/points/grant", { discord_id: grant.discord_id, delta: Number(grant.delta) });
      setMsg({ kind: "ok", text: `Granted. New balance: ${r.data.balance_after}` });
      const u = await api.get("/admin/users"); setUsers(u.data.users);
    } catch (e) {
      setMsg({ kind: "err", text: e?.response?.data?.detail || "Failed" });
    }
  };

  return (
    <section data-testid={ADMIN.root} className="bg-[#0a0a0a] text-[#e8e4d9] min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="max-w-[1400px] mx-auto space-y-10">
        <div>
          <div className="chip chip-red mb-2">OWNER CONSOLE</div>
          <h1 className="font-anton uppercase text-5xl leading-none tracking-tight">Admin</h1>
        </div>

        {msg && (
          <div className={`brutal-border p-3 font-mono text-sm ${msg.kind === "ok" ? "bg-[#e8e4d9] text-black" : "bg-[#da291c] text-[#e8e4d9]"}`}>
            {msg.text}
          </div>
        )}

        {/* Create game */}
        <form data-testid={ADMIN.gameCreate} onSubmit={createGame} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-4">
          <h2 className="font-anton uppercase text-3xl md:col-span-2">Create Stream Game</h2>
          <input data-testid={ADMIN.gameTitle} required placeholder="Title" value={game.title}
            onChange={(e) => setGame({ ...game, title: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono" />
          <select data-testid={ADMIN.gameKind} value={game.kind}
            onChange={(e) => setGame({ ...game, kind: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono">
            <option value="prediction">Prediction</option>
            <option value="quiz">Quiz</option>
            <option value="raffle">Raffle</option>
          </select>
          <input data-testid={ADMIN.gamePrompt} placeholder="Prompt / question" value={game.prompt}
            onChange={(e) => setGame({ ...game, prompt: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono md:col-span-2" />
          <input data-testid={ADMIN.gameOptions} placeholder="Options (comma separated)" value={game.options}
            onChange={(e) => setGame({ ...game, options: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono md:col-span-2" />
          <input data-testid={ADMIN.gameCost} type="number" min="0" placeholder="Entry cost (pts)" value={game.entry_cost}
            onChange={(e) => setGame({ ...game, entry_cost: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono" />
          <input data-testid={ADMIN.gamePool} type="number" min="0" placeholder="Reward pool (pts)" value={game.reward_pool}
            onChange={(e) => setGame({ ...game, reward_pool: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono" />
          <button data-testid={ADMIN.gameSubmit} type="submit"
            className="font-anton uppercase text-lg py-2 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover md:col-span-2">
            Create Game
          </button>
        </form>

        {/* Grant points */}
        <form onSubmit={doGrant} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-3 gap-4">
          <h2 className="font-anton uppercase text-3xl md:col-span-3">Grant Points</h2>
          <input data-testid={ADMIN.grantId} required placeholder="Discord ID" value={grant.discord_id}
            onChange={(e) => setGrant({ ...grant, discord_id: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono md:col-span-2" />
          <input data-testid={ADMIN.grantDelta} type="number" required placeholder="Delta (+/-)" value={grant.delta}
            onChange={(e) => setGrant({ ...grant, delta: e.target.value })}
            className="brutal-border bg-[#e8e4d9] text-black p-2 font-mono" />
          <button data-testid={ADMIN.grantSubmit} type="submit"
            className="font-anton uppercase text-lg py-2 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover md:col-span-3">
            Grant
          </button>
        </form>

        {/* Users table */}
        <div>
          <h2 className="font-anton uppercase text-3xl mb-3">Users ({users.length})</h2>
          <div data-testid={ADMIN.usersTable} className="brutal-border-ivory bg-black overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead>
                <tr className="bg-[#e8e4d9] text-black">
                  <th className="text-left px-3 py-2 uppercase text-xs">Discord ID</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Username</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Email</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Role</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Points</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.discord_id} className="border-t-2 border-[#e8e4d9]/20">
                    <td className="px-3 py-2">{u.discord_id}</td>
                    <td className="px-3 py-2">{u.username}</td>
                    <td className="px-3 py-2 opacity-70">{u.email || "—"}</td>
                    <td className="px-3 py-2">
                      <span className={`chip ${u.role === "owner" ? "chip-red" : ""}`}>{u.role}</span>
                    </td>
                    <td className="px-3 py-2 text-right">{u.points_balance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}
