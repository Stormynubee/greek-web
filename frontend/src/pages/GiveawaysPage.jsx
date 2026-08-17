import { useEffect, useState } from "react";
import { api, describeApiError } from "@/lib/api";
import { GIVEAWAYS } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : "—";

export default function GiveawaysPage() {
  const { user, loginDiscord, refresh } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState({});

  const load = () => {
    setLoading(true);
    setLoadError(null);
    api.get("/giveaways")
      .then(r => setItems(r.data.giveaways))
      .catch(e => setLoadError(describeApiError(e, "Could not load giveaways.")))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const enter = async (g) => {
    if (!user) return loginDiscord();
    setBusy((b) => ({ ...b, [g.id]: true }));
    try {
      const r = await api.post("/giveaways/enter", { giveaway_id: g.id });
      setToast({ kind: "ok", msg: `Entered "${g.title}" · ${r.data.entries} entries` });
      await refresh();
      load();
    } catch (e) {
      setToast({ kind: "err", msg: e?.response?.data?.detail || "Failed to enter" });
    } finally {
      setBusy((b) => ({ ...b, [g.id]: false }));
      setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={GIVEAWAYS.root} className="bg-[#efe9dc] text-black min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="max-w-[1400px] mx-auto">
        <div className="chip chip-red mb-2">GIVEAWAY · SECTION 2</div>
        <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight text-black">
          The <span className="text-[#da291c]">Giveaways</span>
        </h1>
        <p className="font-inter mt-3 max-w-xl opacity-80">
          Free entry, one per user. Winners are drawn randomly by the shogun.
        </p>

        {loadError ? (
          <div role="alert" className="mt-10 brutal-border bg-[#da291c] text-[#efe9dc] p-6 font-mono text-sm">
            <div>{loadError}</div>
            <button type="button" onClick={load} className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase">
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="mt-10 font-mono">Loading...</div>
        ) : items.length === 0 ? (
          <div data-testid={GIVEAWAYS.empty} className="mt-10 brutal-border bg-black text-[#efe9dc] p-8 text-center">
            <div className="font-anton text-3xl uppercase">No giveaways yet</div>
            <p className="font-inter opacity-70 mt-2">Come back soon — new drops appear here.</p>
          </div>
        ) : (
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((g) => {
              const entered = false; // stateless — user can attempt; backend enforces dedup
              const closed = g.status !== "open";
              return (
                <div key={g.id} data-testid={GIVEAWAYS.card(g.id)}
                  className="bg-white brutal-border brutal-shadow flex flex-col">
                  <div className="relative aspect-video bg-[#0a0a0a] brutal-border-b">
                    {g.image_url ? (
                      <img src={g.image_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <img src="/assets/samurai-coin.png" alt="" className="w-24 h-24 object-contain" />
                      </div>
                    )}
                    <div className="absolute top-2 left-2 chip chip-red text-[10px]">{g.status.toUpperCase()}</div>
                    <div className="absolute top-2 right-2 chip text-[10px]">{g.entries} entries</div>
                  </div>
                  <div className="p-4 flex-1 flex flex-col">
                    <h3 className="font-anton uppercase text-2xl leading-tight">{g.title}</h3>
                    <div className="font-mono text-xs uppercase mt-1 text-[#da291c]">Prize: {g.prize}</div>
                    <p className="font-inter text-sm mt-2 opacity-80 flex-1">{g.description}</p>
                    <div className="mt-3 font-mono text-[11px] opacity-70">Ends {fmtDate(g.ends_at)}</div>

                    {g.status === "drawn" && g.winners?.length > 0 && (
                      <div className="mt-3 brutal-border bg-[#efe9dc] p-2 font-mono text-xs">
                        WINNERS: {g.winners.map(w => w.username || w).join(", ")}
                      </div>
                    )}

                    <button
                      data-testid={GIVEAWAYS.enter(g.id)}
                      disabled={closed || busy[g.id]}
                      onClick={() => enter(g)}
                      className="mt-4 font-anton uppercase text-lg py-2 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-40"
                    >
                      {closed ? "Closed" : busy[g.id] ? "Entering..." : user ? "Enter (Free)" : "Login to Enter"}
                    </button>
                  </div>
                </div>
              );
            })}
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
