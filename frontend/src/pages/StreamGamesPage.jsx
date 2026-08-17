import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { GAMES } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

export default function StreamGamesPage() {
  const { user, refresh, loginDiscord } = useAuth();
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [choice, setChoice] = useState({});
  const [busy, setBusy] = useState({});
  const [toast, setToast] = useState(null);

  const load = () => {
    setLoading(true);
    api.get("/games").then((r) => setGames(r.data.games)).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const join = async (g) => {
    if (!user) return loginDiscord();
    setBusy((b) => ({ ...b, [g.id]: true }));
    try {
      await api.post("/games/join", { game_id: g.id, choice: choice[g.id] ?? null });
      setToast({ kind: "ok", msg: `Joined "${g.title}"` });
      await refresh();
    } catch (e) {
      setToast({ kind: "err", msg: e?.response?.data?.detail || "Failed to join" });
    } finally {
      setBusy((b) => ({ ...b, [g.id]: false }));
      setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={GAMES.root} className="bg-[#0a0a0a] text-[#e8e4d9] min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="max-w-[1400px] mx-auto">
        <div className="chip chip-red mb-2">LIVE ARENA</div>
        <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight">
          Stream <span className="text-[#da291c]">Games</span>
        </h1>
        <p className="font-inter opacity-80 mt-3 max-w-xl">
          Predictions, quizzes, raffles. Spend points to enter, earn more when you win.
        </p>

        {loading ? (
          <div className="mt-10 font-mono">Loading...</div>
        ) : games.length === 0 ? (
          <div data-testid={GAMES.empty} className="mt-10 brutal-border-ivory bg-black p-8 text-center">
            <div className="font-anton text-3xl uppercase">No live games right now</div>
            <p className="font-inter opacity-70 mt-2">Follow on Discord to be pinged when the next one drops.</p>
          </div>
        ) : (
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {games.map((g) => (
              <div key={g.id} data-testid={GAMES.card(g.id)} className="brutal-border-ivory bg-[#e8e4d9] text-black p-4 flex flex-col">
                <div className="flex items-center justify-between">
                  <span className="chip">{g.kind.toUpperCase()}</span>
                  <span className={`chip ${g.status === "open" ? "chip-red" : ""}`}>{g.status.toUpperCase()}</span>
                </div>
                <h3 className="font-anton uppercase text-2xl mt-3 leading-tight">{g.title}</h3>
                {g.prompt && <p className="font-inter text-sm mt-2 opacity-80">{g.prompt}</p>}

                {g.options?.length > 0 && (
                  <div className="mt-4 grid gap-2">
                    {g.options.map((opt) => (
                      <label key={opt} data-testid={GAMES.option(g.id, opt)}
                        className={`brutal-border p-2 flex items-center gap-2 cursor-pointer font-mono text-sm
                          ${choice[g.id] === opt ? "bg-[#da291c] text-[#e8e4d9]" : "bg-white"}`}>
                        <input type="radio" name={`opt-${g.id}`} className="accent-[#da291c]"
                          checked={choice[g.id] === opt}
                          onChange={() => setChoice((c) => ({ ...c, [g.id]: opt }))} />
                        {opt}
                      </label>
                    ))}
                  </div>
                )}

                <div className="mt-4 flex items-center justify-between font-mono text-xs uppercase">
                  <span>Entry: {g.entry_cost} pts</span>
                  <span>Pool: {g.reward_pool} pts</span>
                </div>
                <button
                  data-testid={GAMES.join(g.id)}
                  disabled={g.status !== "open" || busy[g.id]}
                  onClick={() => join(g)}
                  className="mt-4 font-anton uppercase text-lg py-2 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow brutal-hover disabled:opacity-40"
                >
                  {g.status !== "open" ? "Closed" : busy[g.id] ? "Joining..." : user ? "Join Game" : "Login to Join"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {toast && (
        <div className={`fixed bottom-16 right-4 brutal-border brutal-shadow px-4 py-3 font-mono text-sm z-50 ${toast.kind === "ok" ? "bg-[#e8e4d9] text-black" : "bg-[#da291c] text-[#e8e4d9]"}`}>
          {toast.msg}
        </div>
      )}
    </section>
  );
}
