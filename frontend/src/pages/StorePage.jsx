import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { STORE } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

export default function StorePage() {
  const { user, refresh, loginDiscord } = useAuth();
  const [rewards, setRewards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState(null); // {id, title, cost}
  const [toast, setToast] = useState(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    api.get("/store/rewards").then((r) => setRewards(r.data.rewards)).finally(() => setLoading(false));
  }, []);

  const doRedeem = async () => {
    if (!confirm) return;
    setPending(true);
    try {
      const key = `redeem_${confirm.id}_${Date.now()}`;
      const r = await api.post("/store/redeem", { reward_id: confirm.id, idempotency_key: key });
      setToast({ kind: "ok", msg: `Redeemed "${r.data.reward}" · new balance ${r.data.balance_after} pts` });
      await refresh();
      // update stock locally
      setRewards((rs) => rs.map(x => x.id === confirm.id && x.stock > 0 ? { ...x, stock: x.stock - 1 } : x));
    } catch (e) {
      setToast({ kind: "err", msg: e?.response?.data?.detail || "Redeem failed" });
    } finally {
      setPending(false);
      setConfirm(null);
      setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={STORE.root} className="bg-[#e8e4d9] text-black min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <div className="chip chip-red mb-2">SAMURAI STORE</div>
            <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight text-black">
              Trade Points · <span className="text-[#da291c]">Get Loot</span>
            </h1>
          </div>
          {user && (
            <div data-testid={STORE.balance} className="chip chip-red text-lg">
              <img src="/assets/samurai-coin.png" alt="" className="w-6 h-6 mr-1" />
              {user.points_balance} pts
            </div>
          )}
        </div>

        {!user && (
          <div className="mt-8 brutal-border bg-black text-[#e8e4d9] p-6 flex flex-wrap items-center gap-4">
            <p className="font-inter flex-1">Sign in with Discord to start earning and redeeming points.</p>
            <button onClick={loginDiscord}
              className="font-anton uppercase text-lg px-4 py-2 bg-[#da291c] brutal-border brutal-shadow-ivory brutal-hover">
              Login with Discord
            </button>
          </div>
        )}

        {loading ? (
          <div className="mt-10 font-mono">Loading rewards...</div>
        ) : (
          <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {rewards.map((r) => {
              const canAfford = user && user.points_balance >= r.cost;
              const inStock = r.stock !== 0;
              return (
                <div key={r.id}
                  data-testid={STORE.card(r.id)}
                  className="bg-white brutal-border brutal-shadow p-4 flex flex-col"
                >
                  <div className="aspect-square bg-[#0a0a0a] brutal-border flex items-center justify-center p-6">
                    <img src={r.image_url || "/assets/samurai-coin.png"} alt="" className="w-full h-full object-contain" />
                  </div>
                  <h3 className="font-anton uppercase text-2xl mt-4 leading-tight">{r.title}</h3>
                  <p className="font-inter text-sm mt-2 opacity-80 flex-1">{r.description}</p>
                  <div className="mt-4 flex items-center justify-between">
                    <div className="chip chip-red text-base"><img src="/assets/samurai-coin.png" alt="" className="w-4 h-4" />{r.cost} pts</div>
                    <div className="font-mono text-xs uppercase opacity-70">
                      {r.stock === -1 ? "∞ stock" : r.stock === 0 ? "Sold out" : `${r.stock} left`}
                    </div>
                  </div>
                  <button
                    data-testid={STORE.redeem(r.id)}
                    disabled={!user || !canAfford || !inStock || pending}
                    onClick={() => setConfirm({ id: r.id, title: r.title, cost: r.cost })}
                    className="mt-4 font-anton uppercase text-lg py-2 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow brutal-hover disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {!user ? "Login to redeem" : !inStock ? "Sold out" : !canAfford ? "Not enough pts" : "Redeem"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Confirm modal */}
      {confirm && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => !pending && setConfirm(null)}>
          <div data-testid={STORE.modal}
            onClick={(e) => e.stopPropagation()}
            className="bg-[#e8e4d9] text-black brutal-border brutal-shadow max-w-md w-full p-6">
            <h3 className="font-anton uppercase text-3xl leading-none">Confirm Redeem</h3>
            <p className="font-inter mt-4">Spend <strong>{confirm.cost} pts</strong> on <strong>{confirm.title}</strong>?</p>
            <div className="mt-6 flex gap-3">
              <button data-testid={STORE.confirm} disabled={pending} onClick={doRedeem}
                className="font-anton uppercase text-lg px-4 py-2 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow brutal-hover flex-1">
                {pending ? "Redeeming..." : "Yes, redeem"}
              </button>
              <button data-testid={STORE.cancel} disabled={pending} onClick={() => setConfirm(null)}
                className="font-mono text-sm uppercase px-4 py-2 border-2 border-black">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div data-testid={STORE.toast}
          className={`fixed bottom-16 right-4 brutal-border brutal-shadow px-4 py-3 font-mono text-sm z-50 ${toast.kind === "ok" ? "bg-[#e8e4d9] text-black" : "bg-[#da291c] text-[#e8e4d9]"}`}>
          {toast.msg}
        </div>
      )}
    </section>
  );
}
