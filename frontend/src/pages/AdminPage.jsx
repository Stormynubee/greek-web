import { useCallback, useEffect, useRef, useState } from "react";
import { api, describeApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Navigate, Link } from "react-router-dom";
import { ADMIN } from "@/constants/testIds";
import CatCrewReference from "@/components/CatCrewReference";

const TABS = ["Overview", "Games", "Weekly Raffles", "Rewards", "Users", "Custom LB", "Live", "Stream Games"];

const Msg = ({ msg }) => msg && (
  <div className={`brutal-border p-3 font-mono text-sm mb-4 ${msg.kind === "ok" ? "bg-[#efe9dc] text-black" : "bg-[#da291c] text-[#efe9dc]"}`}>{msg.text}</div>
);

export default function AdminPage() {
  const { admin, user, loading, adminLogout, logout, refresh } = useAuth();
  const [tab, setTab] = useState("Overview");
  const [msg, setMsg] = useState(null);
  const [loadError, setLoadError] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const refreshController = useRef(null);
  const refreshSequence = useRef(0);

  const [users, setUsers] = useState([]);
  const [games, setGames] = useState([]);
  const [gvs, setGvs] = useState([]);
  const [rewards, setRewards] = useState([]);
  const [customLB, setCustomLB] = useState([]);
  const [live, setLive] = useState({ is_live: false, url: "https://kick.com/greekgodberry" });

  const [gForm, setGForm] = useState({ title: "", kind: "prediction", prompt: "", options: "", entry_cost: 0, reward_pool: 0 });
  const [gwForm, setGwForm] = useState({ title: "", description: "", prize: "", image_url: "", max_winners: 1 });
  const [rForm, setRForm] = useState({ title: "", description: "", cost: 100, stock: -1, image_url: "", category: "custom", requires: "" });
  const [lbForm, setLbForm] = useState({ display_name: "", wagered: 0, bets: 0, board: "monthly" });
  const [grantForm, setGrantForm] = useState({ discord_id: "", delta: "" });

  const refreshAll = useCallback(async ({ fresh = false } = {}) => {
    refreshController.current?.abort();
    const controller = new AbortController();
    refreshController.current = controller;
    const sequence = refreshSequence.current + 1;
    refreshSequence.current = sequence;
    const publicConfig = {
      ...(fresh ? { params: { _refresh: Date.now() } } : {}),
      signal: controller.signal,
    };
    const adminConfig = { signal: controller.signal };
    try {
      const [u, g, gw, r, lb, li] = await Promise.all([
        api.get("/admin/users", adminConfig),
        api.get("/games", publicConfig),
        api.get("/giveaways", publicConfig),
        api.get("/store/rewards", publicConfig),
        api.get("/admin/custom-leaderboard", adminConfig),
        api.get("/live", publicConfig),
      ]);
      if (sequence !== refreshSequence.current) return;
      setUsers(u.data.users); setGames(g.data.games); setGvs(gw.data.giveaways);
      setRewards(r.data.rewards); setCustomLB(lb.data.entries); setLive(li.data);
      setLoadError(null);
    } catch (e) {
      if (e?.code !== "ERR_CANCELED" && sequence === refreshSequence.current) {
        setLoadError(describeApiError(e, "Could not load the owner console."));
        if (e?.response?.status === 401 || e?.response?.status === 403) {
          await refresh();
        }
      }
    }
  }, [refresh]);

  const canAccess = user?.role === "admin" || user?.role === "owner";

  useEffect(() => {
    if (!canAccess) return undefined;
    refreshAll();
    return () => refreshController.current?.abort();
  }, [canAccess, refreshAll]);

  if (loading) return <div className="p-10 font-mono text-[#efe9dc]">Loading...</div>;
  if (!canAccess) return <Navigate to="/login" replace />;

  const ok = (t) => { setMsg({ kind: "ok", text: t }); setTimeout(() => setMsg(null), 3500); };
  const err = (e) => setMsg({ kind: "err", text: describeApiError(e, "The admin action failed.") });
  const runAction = async (operation, successMessage, onSuccess) => {
    setActionBusy(true);
    try {
      const result = await operation();
      if (onSuccess) await onSuccess(result);
      ok(typeof successMessage === "function" ? successMessage(result) : successMessage);
      await refreshAll({ fresh: true });
      return result;
    } catch (e) {
      err(e);
      return null;
    } finally {
      setActionBusy(false);
    }
  };

  const createGame = async (e) => {
    e.preventDefault();
    await runAction(() => api.post("/admin/games", {
        ...gForm, entry_cost: Number(gForm.entry_cost)||0, reward_pool: Number(gForm.reward_pool)||0,
        options: gForm.options.split(",").map(s=>s.trim()).filter(Boolean),
      }), "Game created", () => setGForm({ title:"",kind:"prediction",prompt:"",options:"",entry_cost:0,reward_pool:0 }));
  };
  const resolveGame = async (id, winning) => {
    await runAction(
      () => api.post(`/admin/games/${id}/resolve`, { winning_option: winning || null }),
      "Resolved and paid out",
    );
  };
  const createGw = async (e) => {
    e.preventDefault();
    await runAction(
      () => api.post("/admin/giveaways", { ...gwForm, max_winners: Number(gwForm.max_winners)||1 }),
      "Giveaway created",
      () => setGwForm({ title:"",description:"",prize:"",image_url:"",max_winners:1 }),
    );
  };
  const drawGw = async (id) => {
    await runAction(
      () => api.post(`/admin/giveaways/${id}/draw`),
      (r) => `Winners: ${r.data.winners.map((winner) => winner.username).join(", ")}`,
    );
  };
  const closeGw = async (id) => {
    await runAction(() => api.post(`/admin/giveaways/${id}/close`), "Giveaway closed");
  };
  const createReward = async (e) => {
    e.preventDefault();
    await runAction(
      () => api.post("/admin/rewards", { ...rForm, cost: Number(rForm.cost)||0, stock: Number(rForm.stock) }),
      "Reward added",
      () => setRForm({ title:"",description:"",cost:100,stock:-1,image_url:"",category:"custom",requires:"" }),
    );
  };
  const delReward = async (id) => {
    await runAction(() => api.delete(`/admin/rewards/${id}`), "Reward disabled");
  };
  const addLB = async (e) => {
    e.preventDefault();
    await runAction(
      () => api.post("/admin/custom-leaderboard", { ...lbForm, wagered: Number(lbForm.wagered)||0, bets: Number(lbForm.bets)||0 }),
      "Leaderboard entry added",
      () => setLbForm({ display_name:"",wagered:0,bets:0,board:"monthly" }),
    );
  };
  const delLB = async (id) => {
    await runAction(() => api.delete(`/admin/custom-leaderboard/${id}`), "Leaderboard entry removed");
  };
  const doGrant = async (e) => {
    e.preventDefault();
    const delta = Number(String(grantForm.delta).replace(/[^0-9eE+-]/g, ""));
    if (!Number.isFinite(delta) || delta === 0) {
      window.alert("Enter a non-zero amount (e.g. 100000 or -50000).");
      return;
    }
    await runAction(
      () => api.post("/admin/points/grant", {
        discord_id: grantForm.discord_id,
        delta: Math.trunc(delta),
        idempotency_key: `grant_${grantForm.discord_id}_${Date.now()}`,
      }),
      (r) => `Balance now ${r.data.balance_after.toLocaleString()}`,
      () => { setGrantForm({ discord_id:"", delta:"" }); refreshAll(); },
    );
  };
  const doRevoke = async (discord_id) => {
    await runAction(
      () => api.post("/admin/points/revoke", { discord_id }),
      (r) => `Revoked ${r.data.revoked.toLocaleString()} · balance now ${r.data.balance_after.toLocaleString()}`,
      () => refreshAll(),
    );
  };
  const quickGrant = (amount) => {
    setGrantForm((f) => ({ ...f, delta: String(amount) }));
  };
  const setLiveStatus = async (patch) => {
    await runAction(() => api.post("/admin/live", { ...live, ...patch }), "Live status updated");
  };

  const Input = (p) => (
    <input {...p} className={`brutal-border bg-[#efe9dc] text-black p-2 font-mono ${p.className||""}`} />
  );
  const Btn = ({ children, className: cn, type = "button", ...p }) => (
    <button type={type} {...p} disabled={actionBusy || p.disabled} className={`font-anton uppercase text-lg py-2 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow-ivory brutal-hover disabled:opacity-50 ${cn||""}`}>{children}</button>
  );

  /* eslint-disable react/no-unstable-nested-components */

  return (
    <section data-testid={ADMIN.root} className="bg-[#0a0a0a] text-[#efe9dc] min-h-screen py-8 px-4 sm:px-6 pb-24">
      <div className="code-sequence max-w-[1400px] mx-auto">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <div className="chip chip-red mb-2">SHOGUN&apos;S CONSOLE</div>
            <h1 className="font-anton uppercase text-5xl leading-none tracking-tight">Admin</h1>
            <div className="font-mono text-xs mt-1 opacity-70">
              Signed in as {admin?.username || user?.username} · {admin ? "admin" : "owner"}
            </div>
          </div>
          <CatCrewReference compact />
          <button
            type="button"
            onClick={admin ? adminLogout : logout}
            className="font-mono text-xs uppercase px-3 py-2 border-2 border-[#efe9dc]"
          >
            Logout
          </button>
          <Link
            to="/admin/stream-games"
            className="font-mono text-xs uppercase px-3 py-2 border-2 border-[#efe9dc]"
          >
            Streamer Console
          </Link>
        </div>

        {/* Tab bar */}
        <div className="flex flex-wrap gap-2 mb-6">
          {TABS.map((t) => (
            <button key={t} type="button" onClick={() => setTab(t)}
              data-testid={`admin-tab-${t.toLowerCase().replace(/\s+/g,"-")}`}
              className={`font-anton uppercase text-base px-3 py-2 brutal-border ${tab===t?"bg-[#da291c]":"bg-[#efe9dc] text-black"}`}>
              {t}
            </button>
          ))}
        </div>

        <Msg msg={msg} />
        {loadError && (
          <div className="brutal-border p-3 font-mono text-sm mb-4 bg-[#da291c] text-[#efe9dc]">
            <div>{loadError}</div>
            <button
              type="button"
              disabled={actionBusy}
              onClick={() => refreshAll({ fresh: true })}
              className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase disabled:opacity-50"
            >
              Retry
            </button>
          </div>
        )}

        {/* OVERVIEW */}
        {tab === "Overview" && (
          <div className="grid md:grid-cols-4 gap-4">
            {[
              { k: "Users", v: users.length },
              { k: "Games", v: games.length },
              { k: "Weekly Raffles", v: gvs.length },
              { k: "Rewards", v: rewards.length },
              { k: "Custom LB", v: customLB.length },
              { k: "Live", v: live.is_live ? "ON AIR" : "off-air" },
            ].map(s => (
              <div key={s.k} className="brutal-border-ivory bg-black p-4">
                <div className="font-mono text-xs uppercase opacity-70">{s.k}</div>
                <div className="font-anton text-4xl mt-1">{s.v}</div>
              </div>
            ))}
          </div>
        )}

        {/* GAMES */}
        {tab === "Games" && (
          <div className="space-y-8">
            <form onSubmit={createGame} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-3">
              <h2 className="font-anton uppercase text-2xl md:col-span-2">Create Stream Game</h2>
              <Input placeholder="Title" required value={gForm.title} onChange={(e)=>setGForm({...gForm,title:e.target.value})} />
              <select value={gForm.kind} onChange={(e)=>setGForm({...gForm,kind:e.target.value})} className="brutal-border bg-[#efe9dc] text-black p-2 font-mono">
                <option value="prediction">Prediction</option><option value="quiz">Quiz</option><option value="raffle">Raffle</option>
              </select>
              <Input placeholder="Prompt" value={gForm.prompt} onChange={(e)=>setGForm({...gForm,prompt:e.target.value})} className="md:col-span-2" />
              <Input placeholder="Options (comma separated)" value={gForm.options} onChange={(e)=>setGForm({...gForm,options:e.target.value})} className="md:col-span-2" />
              <Input type="number" placeholder="Entry cost" value={gForm.entry_cost} onChange={(e)=>setGForm({...gForm,entry_cost:e.target.value})} />
              <Input type="number" placeholder="Reward pool" value={gForm.reward_pool} onChange={(e)=>setGForm({...gForm,reward_pool:e.target.value})} />
              <Btn type="submit" className="md:col-span-2">Create Game</Btn>
            </form>

            <div>
              <h3 className="font-anton uppercase text-2xl mb-3">Live Games ({games.length})</h3>
              <div className="brutal-border-ivory bg-black overflow-x-auto">
                <table className="w-full font-mono text-sm">
                  <thead><tr className="bg-[#efe9dc] text-black">
                    <th className="text-left px-3 py-2 uppercase text-xs">Title</th>
                    <th className="text-left px-3 py-2 uppercase text-xs">Kind</th>
                    <th className="text-left px-3 py-2 uppercase text-xs">Status</th>
                    <th className="text-right px-3 py-2 uppercase text-xs">Pool</th>
                    <th className="text-right px-3 py-2 uppercase text-xs">Action</th>
                  </tr></thead>
                  <tbody>
                    {games.map(g => (
                      <tr key={g.id} className="border-t-2 border-[#efe9dc]/20">
                        <td className="px-3 py-2">{g.title}</td>
                        <td className="px-3 py-2">{g.kind}</td>
                        <td className="px-3 py-2">{g.status}</td>
                        <td className="px-3 py-2 text-right">{g.reward_pool}</td>
                        <td className="px-3 py-2 text-right">
                          {g.status === "open" && (
                            <button type="button" onClick={() => {
                              const w = g.options?.length ? prompt("Winning option (or empty for any):", "") : null;
                              resolveGame(g.id, w);
                            }} disabled={actionBusy} className="font-mono text-xs uppercase px-2 py-1 bg-[#da291c] text-[#efe9dc] disabled:opacity-50">Resolve</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* WEEKLY RAFFLES */}
        {tab === "Weekly Raffles" && (
          <div className="space-y-8">
            <form onSubmit={createGw} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-3">
              <h2 className="font-anton uppercase text-2xl md:col-span-2">Create Weekly Raffle</h2>
              <Input placeholder="Title" required value={gwForm.title} onChange={(e)=>setGwForm({...gwForm,title:e.target.value})} />
              <Input placeholder="Prize" required value={gwForm.prize} onChange={(e)=>setGwForm({...gwForm,prize:e.target.value})} />
              <Input placeholder="Description" value={gwForm.description} onChange={(e)=>setGwForm({...gwForm,description:e.target.value})} className="md:col-span-2" />
              <Input placeholder="Image URL (optional)" value={gwForm.image_url} onChange={(e)=>setGwForm({...gwForm,image_url:e.target.value})} />
              <Input type="number" min="1" placeholder="Max winners" value={gwForm.max_winners} onChange={(e)=>setGwForm({...gwForm,max_winners:e.target.value})} />
              <Btn type="submit" className="md:col-span-2">Create</Btn>
            </form>

            <div className="grid md:grid-cols-2 gap-4">
              {gvs.map(g => (
                <div key={g.id} className="brutal-border-ivory bg-black p-4">
                  <div className="flex items-center justify-between">
                    <h3 className="font-anton uppercase text-xl">{g.title}</h3>
                    <span className="chip chip-red text-[10px]">{g.status}</span>
                  </div>
                  <div className="font-mono text-xs mt-1 opacity-80">Prize: {g.prize}</div>
                  <div className="font-mono text-xs opacity-60">{g.entries} entries · max winners {g.max_winners}</div>
                  {g.winners?.length > 0 && (
                    <div className="mt-2 font-mono text-xs">Winners: {g.winners.map(w => w.username || w).join(", ")}</div>
                  )}
                  <div className="mt-3 flex gap-2">
                    {g.status === "open" && <>
                      <button type="button" disabled={actionBusy} onClick={() => drawGw(g.id)} className="font-mono text-xs uppercase px-3 py-1 bg-[#da291c] text-[#efe9dc] disabled:opacity-50">Draw Winner</button>
                      <button type="button" disabled={actionBusy} onClick={() => closeGw(g.id)} className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc] disabled:opacity-50">Close</button>
                    </>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* REWARDS */}
        {tab === "Rewards" && (
          <div className="space-y-8">
            <form onSubmit={createReward} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-3">
              <h2 className="font-anton uppercase text-2xl md:col-span-2">Add Reward</h2>
              <Input placeholder="Title" required value={rForm.title} onChange={(e)=>setRForm({...rForm,title:e.target.value})} />
              <Input placeholder="Category (bonus/tip/custom/vip)" value={rForm.category} onChange={(e)=>setRForm({...rForm,category:e.target.value})} />
              <Input placeholder="Description" value={rForm.description} onChange={(e)=>setRForm({...rForm,description:e.target.value})} className="md:col-span-2" />
              <Input type="number" placeholder="Cost (pts)" value={rForm.cost} onChange={(e)=>setRForm({...rForm,cost:e.target.value})} />
              <Input type="number" placeholder="Stock (-1 unlimited)" value={rForm.stock} onChange={(e)=>setRForm({...rForm,stock:e.target.value})} />
              <Input placeholder="Image URL (optional)" value={rForm.image_url} onChange={(e)=>setRForm({...rForm,image_url:e.target.value})} />
              <Input placeholder="Requires (optional)" value={rForm.requires} onChange={(e)=>setRForm({...rForm,requires:e.target.value})} />
              <Btn type="submit" className="md:col-span-2">Add Reward</Btn>
            </form>

            <div className="grid md:grid-cols-3 gap-3">
              {rewards.map(r => (
                <div key={r.id} className="brutal-border-ivory bg-black p-3">
                  <div className="font-anton uppercase text-lg leading-tight">{r.title}</div>
                  <div className="font-mono text-xs opacity-70 mt-1">{r.category} · {r.cost} pts · {r.stock === -1 ? "∞" : r.stock} stock</div>
                  <button type="button" disabled={actionBusy} onClick={() => delReward(r.id)} className="mt-2 font-mono text-[10px] uppercase px-2 py-1 border-2 border-[#efe9dc] disabled:opacity-50">Disable</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* USERS */}
        {tab === "Users" && (
          <div className="space-y-6">
            <form onSubmit={doGrant} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-3 gap-3">
              <h2 className="font-anton uppercase text-2xl md:col-span-3">Grant Points</h2>
              <Input placeholder="Discord ID" required value={grantForm.discord_id} onChange={(e)=>setGrantForm({...grantForm,discord_id:e.target.value})} className="md:col-span-2" />
              <Input type="text" inputMode="numeric" placeholder="Amount (e.g. 500, 1000, -250)" required value={grantForm.delta} onChange={(e)=>setGrantForm({...grantForm,delta:e.target.value.replace(/[^\d-]/g,"")})} />
              <div className="flex flex-wrap gap-2 md:col-span-3">
                <span className="font-mono text-xs uppercase self-center opacity-50">Grant +</span>
                {[100, 250, 500, 1000, 5000, 10000].map((amt) => (
                  <button
                    key={amt}
                    type="button"
                    disabled={actionBusy}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => quickGrant(amt)}
                    className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc]/60 hover:bg-[#efe9dc] hover:text-black disabled:opacity-50"
                  >
                    +{amt.toLocaleString()}
                  </button>
                ))}
                <span className="font-mono text-xs uppercase self-center opacity-50 ml-2">Revoke −</span>
                {[100, 250, 500, 1000, 5000, 10000].map((amt) => (
                  <button
                    key={`-${amt}`}
                    type="button"
                    disabled={actionBusy}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => quickGrant(-amt)}
                    className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc]/60 hover:bg-[#efe9dc] hover:text-black disabled:opacity-50"
                  >
                    −{amt.toLocaleString()}
                  </button>
                ))}
                <span className="ml-auto font-mono text-xs opacity-60 self-center">Amount = coins · click a chip or type</span>
              </div>
              <Btn type="submit" className="md:col-span-3">Grant</Btn>
            </form>
            <div className="brutal-border-ivory bg-black overflow-x-auto">
              <table className="w-full font-mono text-sm">
                <thead><tr className="bg-[#efe9dc] text-black">
                  <th className="text-left px-3 py-2 uppercase text-xs">Discord ID</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Username</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Role</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Points</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Last Grant</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Action</th>
                </tr></thead>
                <tbody>{users.map(u => (
                  <tr key={u.discord_id} className="border-t-2 border-[#efe9dc]/20">
                    <td className="px-3 py-2">{u.discord_id}</td>
                    <td className="px-3 py-2">{u.username}</td>
                    <td className="px-3 py-2">{u.role}</td>
                    <td className="px-3 py-2 text-right">{Number(u.points_balance).toLocaleString()}</td>
                    <td className="px-3 py-2 text-right">
                      {u.last_grant ? (
                        <span className={u.last_grant > 0 ? "text-[#9ed6a5]" : "text-[#da291c]"}>
                          {u.last_grant > 0 ? "+" : ""}{Number(u.last_grant).toLocaleString()}
                        </span>
                      ) : <span className="opacity-40">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        disabled={actionBusy || !u.last_grant}
                        onClick={() => doRevoke(u.discord_id)}
                        className="font-mono text-[10px] uppercase px-2 py-1 border-2 border-[#da291c] text-[#da291c] disabled:opacity-30"
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        )}

        {/* CUSTOM LB */}
        {tab === "Custom LB" && (
          <div className="space-y-6">
            <form onSubmit={addLB} className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-3">
              <h2 className="font-anton uppercase text-2xl md:col-span-2">Add manual leaderboard entry</h2>
              <Input placeholder="Display name" required value={lbForm.display_name} onChange={(e)=>setLbForm({...lbForm,display_name:e.target.value})} />
              <select value={lbForm.board} onChange={(e)=>setLbForm({...lbForm,board:e.target.value})} className="brutal-border bg-[#efe9dc] text-black p-2 font-mono">
                <option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option>
              </select>
              <Input type="number" step="0.01" placeholder="Wagered ($)" value={lbForm.wagered} onChange={(e)=>setLbForm({...lbForm,wagered:e.target.value})} />
              <Input type="number" placeholder="Bets" value={lbForm.bets} onChange={(e)=>setLbForm({...lbForm,bets:e.target.value})} />
              <Btn type="submit" className="md:col-span-2">Add</Btn>
            </form>
            <div className="brutal-border-ivory bg-black overflow-x-auto">
              <table className="w-full font-mono text-sm">
                <thead><tr className="bg-[#efe9dc] text-black">
                  <th className="text-left px-3 py-2 uppercase text-xs">Name</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Board</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Wagered</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Bets</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Action</th>
                </tr></thead>
                <tbody>{customLB.map(e => (
                  <tr key={e.id} className="border-t-2 border-[#efe9dc]/20">
                    <td className="px-3 py-2">{e.display_name}</td>
                    <td className="px-3 py-2">{e.board}</td>
                    <td className="px-3 py-2 text-right">${e.wagered}</td>
                    <td className="px-3 py-2 text-right">{e.bets}</td>
                    <td className="px-3 py-2 text-right"><button type="button" disabled={actionBusy} onClick={()=>delLB(e.id)} className="font-mono text-[10px] uppercase px-2 py-1 border-2 border-[#da291c] text-[#da291c] disabled:opacity-50">Remove</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        )}

        {/* LIVE */}
        {tab === "Live" && (
          <div className="brutal-border-ivory bg-black p-6 space-y-4 max-w-2xl">
            <h2 className="font-anton uppercase text-2xl">Live Status</h2>
            <div className="flex items-center gap-3">
              <span className="font-mono text-sm">Current: </span>
              <span className={`chip ${live.is_live ? "chip-red animate-pulse" : ""}`}>{live.is_live ? `LIVE ON ${live.platform?.toUpperCase()}` : "OFF-AIR"}</span>
            </div>
            <div className="grid gap-3">
              <Input placeholder="Stream URL" value={live.url || ""} onChange={(e)=>setLive({...live,url:e.target.value})} />
              <Input placeholder="Stream title (optional)" value={live.title || ""} onChange={(e)=>setLive({...live,title:e.target.value})} />
              <select value={live.platform || "kick"} onChange={(e)=>setLive({...live,platform:e.target.value})} className="brutal-border bg-[#efe9dc] text-black p-2 font-mono">
                <option value="kick">Kick</option><option value="twitch">Twitch</option><option value="youtube">YouTube</option>
              </select>
            </div>
            <div className="flex gap-3">
              <Btn onClick={() => setLiveStatus({ is_live: true })}>Go LIVE</Btn>
              <button type="button" disabled={actionBusy} onClick={() => setLiveStatus({ is_live: false })} className="font-anton uppercase text-lg py-2 px-4 border-2 border-[#efe9dc] disabled:opacity-50">End Stream</button>
            </div>
          </div>
        )}

        {/* STREAM GAMES (Kick/Twitch control via greek-bingo backend) —
            moved to the standalone /admin/stream-games console so a main-site
            logout no longer tears it down. */}
        {tab === "Stream Games" && (
          <div className="brutal-border-ivory bg-black p-6">
            <h3 className="font-anton uppercase text-xl">Stream Games Console</h3>
            <p className="font-inter text-sm mt-2 opacity-80">
              The stream-game console now runs on its own page with its own Discord
              login — independent of this admin dashboard.
            </p>
            <Link
              to="/admin/stream-games"
              className="font-anton uppercase text-sm py-2 px-4 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover inline-block mt-4"
            >
              Open Streamer Console
            </Link>
          </div>
        )}
      </div>
    </section>
  );
}
