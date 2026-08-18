import { useCallback, useEffect, useRef, useState } from "react";
import { api, describeApiError } from "@/lib/api";
import { STORE, POINT_SHOP } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

const fmtDate = (iso) => iso ? new Date(iso).toLocaleDateString() : "—";
const isRainbetReward = (reward) =>
  [reward?.title, reward?.description, reward?.requires]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes("rainbet");
const TABS = [
  { key: "shop", label: "Shop", tid: POINT_SHOP.tabShop },
  { key: "history", label: "My History", tid: POINT_SHOP.tabHistory },
  { key: "redemptions", label: "My Redemptions", tid: POINT_SHOP.tabRedemptions },
  { key: "leaderboard", label: "Leaderboard", tid: POINT_SHOP.tabLeaderboard },
];
const PanelError = ({ message, onRetry }) => (
  <div role="alert" className="mt-6 brutal-border bg-[#da291c] text-[#efe9dc] p-4 font-mono text-sm">
    <div>{message}</div>
    <button type="button" onClick={onRetry} className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase">
      Retry
    </button>
  </div>
);

export default function StorePage() {
  const { user, refresh, loginDiscord } = useAuth();
  const [tab, setTab] = useState("shop");
  const [rewards, setRewards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [panelError, setPanelError] = useState(null);
  const [confirm, setConfirm] = useState(null);
  const [toast, setToast] = useState(null);
  const [pending, setPending] = useState(false);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelAttempt, setPanelAttempt] = useState(0);
  const [history, setHistory] = useState([]);
  const [reds, setReds] = useState([]);
  const [lb, setLb] = useState([]);
  const rewardsRequest = useRef(null);
  const rewardsSequence = useRef(0);
  const panelRequest = useRef(null);
  const panelSequence = useRef(0);

  const loadRewards = useCallback(({ fresh = false } = {}) => {
    rewardsRequest.current?.abort();
    const controller = new AbortController();
    rewardsRequest.current = controller;
    const sequence = rewardsSequence.current + 1;
    rewardsSequence.current = sequence;
    setLoading(true);
    setLoadError(null);
    api.get("/store/rewards", {
      params: fresh ? { _refresh: Date.now() } : undefined,
      signal: controller.signal,
    })
      .then((r) => {
        if (sequence === rewardsSequence.current) {
          setRewards((r.data.rewards || []).filter((reward) => !isRainbetReward(reward)));
        }
      })
      .catch((e) => {
        if (e?.code !== "ERR_CANCELED" && sequence === rewardsSequence.current) {
          setLoadError(describeApiError(e, "Could not load rewards."));
        }
      })
      .finally(() => {
        if (sequence === rewardsSequence.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    loadRewards();
    return () => rewardsRequest.current?.abort();
  }, [loadRewards]);

  useEffect(() => {
    panelRequest.current?.abort();
    const controller = new AbortController();
    panelRequest.current = controller;
    const sequence = panelSequence.current + 1;
    panelSequence.current = sequence;
    setPanelError(null);
    if ((tab === "history" || tab === "redemptions") && !user) {
      setPanelLoading(false);
      return () => controller.abort();
    }
    if (tab === "shop") {
      setPanelLoading(false);
      return () => controller.abort();
    }

    setPanelLoading(true);
    const request = tab === "history"
      ? api.get("/points/ledger", { signal: controller.signal })
      : tab === "redemptions"
        ? api.get("/points/redemptions", { signal: controller.signal })
        : api.get("/points/leaderboard", { signal: controller.signal });
    request
      .then((r) => {
        if (sequence !== panelSequence.current) return;
        if (tab === "history") setHistory(r.data.entries);
        else if (tab === "redemptions") setReds(r.data.redemptions);
        else setLb(r.data.leaderboard);
      })
      .catch((e) => {
        if (e?.code !== "ERR_CANCELED" && sequence === panelSequence.current) {
          const fallback = tab === "history"
            ? "Could not load point history."
            : tab === "redemptions"
              ? "Could not load redemptions."
              : "Could not load the points leaderboard.";
          setPanelError(describeApiError(e, fallback));
        }
      })
      .finally(() => {
        if (sequence === panelSequence.current) setPanelLoading(false);
      });
    return () => controller.abort();
  }, [tab, user, panelAttempt]);

  const doRedeem = async () => {
    if (!confirm) return;
    setPending(true);
    try {
      const key = `redeem_${confirm.id}_${Date.now()}`;
      const r = await api.post("/store/redeem", { reward_id: confirm.id, idempotency_key: key });
      setToast({ kind: "ok", msg: `Redeemed "${r.data.reward}" · new balance ${r.data.balance_after} pts` });
      await refresh();
      loadRewards({ fresh: true });
    } catch (e) {
      setToast({ kind: "err", msg: describeApiError(e, "Redeem failed.") });
    } finally {
      setPending(false); setConfirm(null); setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={STORE.root} className="store-page relative overflow-hidden bg-[#0a0a0a] text-[#efe9dc] min-h-screen py-8 px-4 sm:px-6 pb-24">
      <div aria-hidden className="store-coin-float absolute top-4 sm:top-8 right-4 sm:right-16 z-0 pointer-events-none">
        <img
          src="/assets/samurai-coin.png"
          alt=""
          width="160"
          height="160"
          decoding="async"
          className="w-32 sm:w-48 h-32 sm:h-48 object-contain"
        />
      </div>
      <div className="code-sequence relative z-[1] max-w-[1400px] mx-auto">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="chip chip-red mb-2">POINT SHOP</div>
            <h1 className="store-heading font-anton uppercase text-4xl sm:text-6xl leading-none tracking-tight">
              Trade Points · <span className="text-[#da291c]">Get Loot</span>
            </h1>
          </div>
          {user && (
            <div data-testid={STORE.balance} className="chip chip-red text-lg">
              <img
                src="/assets/samurai-coin.png"
                alt=""
                width="24"
                height="24"
                decoding="async"
                className="w-6 h-6 mr-1"
              />
              {user.points_balance} pts
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="store-tabs mt-6 border-b-2 border-[#efe9dc]/20 flex gap-1 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.key} data-testid={t.tid} onClick={() => setTab(t.key)}
              className={`font-anton uppercase text-base px-4 py-2 border-b-4 ${tab===t.key ? "border-[#da291c] text-[#da291c]" : "border-transparent text-[#efe9dc]/70"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "shop" && (
          <>
            {loadError && (
              <div role="alert" className="mt-6 brutal-border bg-[#da291c] text-[#efe9dc] p-4 font-mono text-sm">
                <div>{loadError}</div>
                <button type="button" onClick={() => loadRewards({ fresh: true })} className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase">
                  Retry
                </button>
              </div>
            )}
            {!user && !loadError && (
              <div className="mt-6 brutal-border bg-black text-[#efe9dc] p-4 flex flex-wrap items-center gap-3">
                <p className="font-inter flex-1">Sign in with Discord to start earning and redeeming points.</p>
                <button onClick={loginDiscord} className="font-anton uppercase text-base px-3 py-2 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover">Login with Discord</button>
              </div>
            )}
            <section className="store-earn-panel mt-6" aria-labelledby="store-earn-title">
              <div className="store-earn-panel-header">
                <div>
                  <div className="chip chip-red mb-2">LOCKLY // GREEK33</div>
                  <h2 id="store-earn-title" className="font-anton uppercase text-3xl sm:text-4xl leading-none">
                    How to earn points
                  </h2>
                </div>
                <span className="store-earn-live font-mono text-[10px] uppercase">Live rules</span>
              </div>
              <div className="store-earn-grid">
                <div className="store-earn-rule">
                  <span className="store-earn-index">01</span>
                  <div>
                    <strong>1 pt per $50 wagered on Lockly</strong>
                    <p>Use code <b>GREEK33</b> when you play.</p>
                  </div>
                </div>
                <div className="store-earn-rule">
                  <span className="store-earn-index">02</span>
                  <div>
                    <strong>1 pt per Kick chat message</strong>
                    <p>One point every <b>180 seconds</b>.</p>
                  </div>
                </div>
                <div className="store-earn-rule">
                  <span className="store-earn-index">03</span>
                  <div>
                    <strong>1 pt per Twitch chat message</strong>
                    <p>One point every <b>180 seconds</b>.</p>
                  </div>
                </div>
                <div className="store-earn-rule">
                  <span className="store-earn-index">04</span>
                  <div>
                    <strong>15 pts per hour watching the stream</strong>
                    <p>Stay tuned in while the stream is live.</p>
                  </div>
                </div>
              </div>
            </section>
            {loading ? <div className="mt-8 font-mono">Loading rewards...</div> : !loadError && (
              <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {rewards.map((r) => {
                  const canAfford = user && user.points_balance >= r.cost;
                  const inStock = r.stock !== 0;
                  return (
                    <div key={r.id} data-testid={STORE.card(r.id)} className="bg-[#1a1a1a] brutal-border-ivory flex flex-col">
                      <div className="store-reward-media bg-[#0a0a0a] border-b-2 border-[#efe9dc]/20 flex items-center justify-center p-4">
                        <img
                          src={r.image_url || "/assets/samurai-coin.png"}
                          alt=""
                          loading="lazy"
                          decoding="async"
                          width="320"
                          height="180"
                          className="max-w-full max-h-full w-auto h-auto object-contain"
                        />
                      </div>
                      <div className="p-3 flex-1 flex flex-col">
                        <h3 className="font-anton uppercase text-base leading-tight">{r.title}</h3>
                        <div className="font-mono text-[10px] uppercase mt-1 text-[#efe9dc]/60">{r.category}</div>
                        <p className="font-inter text-xs mt-2 opacity-80 flex-1">{r.description}</p>
                        <div className="mt-3 flex items-center justify-between">
                          <span className="font-anton text-xl text-[#da291c]">{r.cost.toLocaleString()} pts</span>
                          <button
                            data-testid={STORE.redeem(r.id)}
                            disabled={pending || (Boolean(user) && (!canAfford || !inStock))}
                            onClick={() => {
                              if (!user) return loginDiscord();
                              setConfirm({ id: r.id, title: r.title, cost: r.cost });
                            }}
                            className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc] hover:bg-[#efe9dc] hover:text-black disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                            {!user ? "Sign in" : !inStock ? "Sold out" : canAfford ? "Redeem" : "Locked"}
                          </button>
                        </div>
                        {r.requires && <div className="mt-2 font-mono text-[10px] opacity-60">Requires: {r.requires}</div>}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}

        {tab === "history" && (
          !user ? <div className="mt-6 font-mono opacity-70">Login to see your history.</div> :
          panelError ? <PanelError message={panelError} onRetry={() => setPanelAttempt((value) => value + 1)} /> :
          panelLoading ? <div className="mt-6 font-mono">Loading point history...</div> :
          <div className="mt-6 brutal-border-ivory bg-black overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead><tr className="bg-[#efe9dc] text-black">
                <th className="text-left px-3 py-2 uppercase text-xs">When</th>
                <th className="text-left px-3 py-2 uppercase text-xs">Reason</th>
                <th className="text-right px-3 py-2 uppercase text-xs">Delta</th>
                <th className="text-right px-3 py-2 uppercase text-xs">Balance</th>
              </tr></thead>
              <tbody>{history.map((h, i) => (
                <tr key={i} className="border-t-2 border-[#efe9dc]/20">
                  <td className="px-3 py-2">{fmtDate(h.created_at)}</td>
                  <td className="px-3 py-2">{h.reason}</td>
                  <td className={`px-3 py-2 text-right ${h.delta < 0 ? "text-[#da291c]" : "text-[#7ee787]"}`}>{h.delta > 0 ? "+" : ""}{h.delta}</td>
                  <td className="px-3 py-2 text-right">{h.balance_after}</td>
                </tr>
              ))}</tbody>
            </table>
            {history.length === 0 && <div className="p-4 font-mono text-xs opacity-70">No activity yet.</div>}
          </div>
        )}

        {tab === "redemptions" && (
          !user ? <div className="mt-6 font-mono opacity-70">Login to see your redemptions.</div> :
          panelError ? <PanelError message={panelError} onRetry={() => setPanelAttempt((value) => value + 1)} /> :
          panelLoading ? <div className="mt-6 font-mono">Loading redemptions...</div> :
          <div className="mt-6 grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {reds.map((r, i) => (
              <div key={i} className="brutal-border-ivory bg-black p-4">
                <div className="font-anton uppercase text-lg leading-tight">{r.reward_title}</div>
                <div className="font-mono text-xs opacity-70 mt-1">Cost: {r.cost} pts · {fmtDate(r.created_at)}</div>
                <div className="mt-2 chip chip-red text-[10px]">Pending fulfilment</div>
              </div>
            ))}
            {reds.length === 0 && <div className="font-mono text-xs opacity-70">No redemptions yet.</div>}
          </div>
        )}

        {tab === "leaderboard" && (
          panelError ? <PanelError message={panelError} onRetry={() => setPanelAttempt((value) => value + 1)} /> :
          panelLoading ? <div className="mt-6 font-mono">Loading points leaderboard...</div> :
          <div className="mt-6 brutal-border-ivory bg-black overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead><tr className="bg-[#efe9dc] text-black">
                <th className="text-left px-3 py-2 uppercase text-xs">#</th>
                <th className="text-left px-3 py-2 uppercase text-xs">Member</th>
                <th className="text-right px-3 py-2 uppercase text-xs">Points</th>
              </tr></thead>
              <tbody>{lb.map(row => (
                <tr key={row.rank} className="border-t-2 border-[#efe9dc]/20">
                  <td className="px-3 py-2 font-anton text-lg">{row.rank}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-2">
                      {row.avatar_url && (
                        <img
                          src={row.avatar_url}
                          alt=""
                          width="24"
                          height="24"
                          decoding="async"
                          className="w-6 h-6 border-2 border-[#efe9dc]"
                        />
                      )}
                      {row.username}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-[#da291c]">{row.points}</td>
                </tr>
              ))}</tbody>
            </table>
            {lb.length === 0 && <div className="p-4 font-mono text-xs opacity-70">No point holders yet.</div>}
          </div>
        )}
      </div>

      {confirm && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => !pending && setConfirm(null)}>
          <div data-testid={STORE.modal} onClick={(e) => e.stopPropagation()}
            className="bg-[#efe9dc] text-black brutal-border brutal-shadow max-w-md w-full p-6">
            <h3 className="font-anton uppercase text-3xl leading-none">Confirm Redeem</h3>
            <p className="font-inter mt-4">Spend <strong>{confirm.cost} pts</strong> on <strong>{confirm.title}</strong>?</p>
            <div className="mt-6 flex gap-3">
              <button data-testid={STORE.confirm} disabled={pending} onClick={doRedeem}
                className="font-anton uppercase text-lg px-4 py-2 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover flex-1">
                {pending ? "Redeeming..." : "Yes, redeem"}
              </button>
              <button data-testid={STORE.cancel} disabled={pending} onClick={() => setConfirm(null)}
                className="font-mono text-sm uppercase px-4 py-2 border-2 border-black">Cancel</button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div data-testid={STORE.toast}
          className={`store-toast fixed bottom-16 right-4 brutal-border brutal-shadow px-4 py-3 font-mono text-sm z-50 ${toast.kind === "ok" ? "bg-[#efe9dc] text-black" : "bg-[#da291c] text-[#efe9dc]"}`}>
          {toast.msg}
        </div>
      )}
    </section>
  );
}
