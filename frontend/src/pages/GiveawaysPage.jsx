import { useCallback, useEffect, useRef, useState } from "react";
import { api, describeApiError } from "@/lib/api";
import { GIVEAWAYS } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : "—";
const WEEKLY_RAFFLE_COPY = "Meet this week's wagering requirement of $250 on Lockly under code GREEK33, and you're automatically entered — a $25 bonus buy is drawn every Monday live on stream.";
const PREVIOUS_WINNERS = [
  { week: "Week 1", username: "filip_1336" },
];

export default function GiveawaysPage() {
  const { user, loginDiscord, refresh } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState({});
  const requestController = useRef(null);
  const requestSequence = useRef(0);

  const load = useCallback(({ fresh = false } = {}) => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setLoading(true);
    setLoadError(null);
    api.get("/giveaways", {
      params: fresh ? { _refresh: Date.now() } : undefined,
      signal: controller.signal,
    })
      .then((r) => {
        if (sequence === requestSequence.current) setItems(r.data.giveaways);
      })
      .catch((e) => {
        if (e?.code !== "ERR_CANCELED" && sequence === requestSequence.current) {
          setLoadError(describeApiError(e, "Could not load giveaways."));
        }
      })
      .finally(() => {
        if (sequence === requestSequence.current) setLoading(false);
      });
  }, []);
  useEffect(() => {
    load();
    return () => requestController.current?.abort();
  }, [load]);

  const enter = async (g) => {
    if (!user) return loginDiscord();
    setBusy((b) => ({ ...b, [g.id]: true }));
    try {
      const r = await api.post("/giveaways/enter", { giveaway_id: g.id });
      setToast({ kind: "ok", msg: `Entered "${g.title}" · ${r.data.entries} entries` });
      await refresh();
      load({ fresh: true });
    } catch (e) {
      setToast({ kind: "err", msg: describeApiError(e, "Failed to enter the giveaway.") });
    } finally {
      setBusy((b) => ({ ...b, [g.id]: false }));
      setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={GIVEAWAYS.root} className="weekly-raffle-page min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="code-sequence max-w-[980px] mx-auto">
        <div className="weekly-raffle-kicker">
          <span className="chip chip-red">NO PURCHASE NEEDED</span>
          <span className="weekly-raffle-status">MONDAY <i /> LIVE DRAW</span>
        </div>
        <h1 className="weekly-raffle-title font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight">
          Weekly <span>Raffle</span>
        </h1>
        <p className="weekly-raffle-lede font-inter mt-4 max-w-2xl">
          Meet this week's wagering requirement of <strong>$250</strong> on Lockly under code <strong>GREEK33</strong>, and you're automatically entered — a <strong>$25 bonus buy</strong> is drawn every Monday live on stream.
        </p>
        <div className="weekly-raffle-signals mt-6" aria-label="Weekly raffle details">
          <span><b>01</b> Lockly / GREEK33</span>
          <span><b>02</b> $250 wager requirement</span>
          <span><b>03</b> $25 bonus buy · Mondays</span>
        </div>

        {loadError ? (
          <div role="alert" className="mt-10 brutal-border bg-[#da291c] text-[#efe9dc] p-6 font-mono text-sm">
            <div>{loadError}</div>
            <button type="button" onClick={() => load({ fresh: true })} className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase">
              Retry
            </button>
          </div>
        ) : loading ? (
          <div className="mt-10 font-mono">Loading...</div>
        ) : items.length === 0 ? (
          <div data-testid={GIVEAWAYS.empty} className="weekly-raffle-empty mt-10">
            <div className="weekly-raffle-empty-mark" aria-hidden>
              <span />
              <span />
              <span />
            </div>
            <div className="weekly-raffle-empty-copy">
              <div className="weekly-raffle-empty-label">STATUS // STANDBY</div>
              <div className="font-anton text-3xl uppercase mt-2">No raffle is open</div>
              <p className="font-inter opacity-70 mt-2">No raffle is open for this week yet — check back soon.</p>
            </div>
          </div>
        ) : (
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((g) => {
              const closed = g.status !== "open";
              return (
                <div key={g.id} data-testid={GIVEAWAYS.card(g.id)}
                  className="weekly-raffle-card brutal-border-ivory brutal-shadow-red flex flex-col">
                  <div className="relative aspect-video bg-[#0a0a0a] border-b-2 border-[#efe9dc]/20">
                    {g.image_url ? (
                      <img
                        src={g.image_url}
                        alt=""
                        width="640"
                        height="360"
                        loading="lazy"
                        decoding="async"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <img
                          src="/assets/samurai-coin.png"
                          alt=""
                          width="96"
                          height="96"
                          decoding="async"
                          className="w-24 h-24 object-contain"
                        />
                      </div>
                    )}
                    <div className="absolute top-2 left-2 chip chip-red text-[10px]">{g.status.toUpperCase()}</div>
                    <div className="absolute top-2 right-2 chip text-[10px]">{g.entries} entries</div>
                  </div>
                  <div className="p-4 flex-1 flex flex-col">
                    <h3 className="font-anton uppercase text-2xl leading-tight">{g.title}</h3>
                    <div className="font-mono text-xs uppercase mt-1 text-[#da291c]">Prize: {g.prize}</div>
                    <p className="font-inter text-sm mt-2 text-[#efe9dc]/75 flex-1">{g.description || WEEKLY_RAFFLE_COPY}</p>
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

        <section className="weekly-raffle-winners mt-10" aria-labelledby="previous-winners-title">
          <div className="weekly-raffle-archive-label">ARCHIVE // WINNER LOG</div>
          <h2 id="previous-winners-title" className="font-anton uppercase text-xl tracking-wide">
            <span aria-hidden>+</span> Previous Winner
          </h2>
          <div className="mt-4 grid gap-2">
            {PREVIOUS_WINNERS.map((winner) => (
              <div className="weekly-raffle-winner" key={`${winner.week}-${winner.username}`}>
                <span>{winner.week}</span>
                <strong>{winner.username}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>

      {toast && (
        <div className={`fixed bottom-16 right-4 brutal-border brutal-shadow px-4 py-3 font-mono text-sm z-50 ${toast.kind === "ok" ? "bg-[#e8e4d9] text-black" : "bg-[#da291c] text-[#e8e4d9]"}`}>
          {toast.msg}
        </div>
      )}
    </section>
  );
}
