import { useCallback, useEffect, useRef, useState } from "react";
import { api, describeApiError } from "@/lib/api";
import { GAMES } from "@/constants/testIds";
import { useAuth } from "@/contexts/AuthContext";

export default function StreamGamesPage() {
  const { user, refresh, loginDiscord } = useAuth();
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [choice, setChoice] = useState({});
  const [busy, setBusy] = useState({});
  const [toast, setToast] = useState(null);
  const [cerberus, setCerberus] = useState(null);
  const [bingo, setBingo] = useState(null);
  const [liveFeedError, setLiveFeedError] = useState(null);
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
    api.get("/games", {
      params: fresh ? { _refresh: Date.now() } : undefined,
      signal: controller.signal,
    })
      .then((r) => {
        if (sequence === requestSequence.current) setGames(r.data.games);
      })
      .catch((e) => {
        if (e?.code !== "ERR_CANCELED" && sequence === requestSequence.current) {
          setLoadError(describeApiError(e, "Could not load stream games."));
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

  const loadLiveFeeds = useCallback(() => {
    Promise.allSettled([
      api.get("/cerberus/live-state"),
      api.get("/bingo/active"),
    ]).then(([cerberusResult, bingoResult]) => {
      if (cerberusResult.status === "fulfilled") setCerberus(cerberusResult.value.data);
      if (bingoResult.status === "fulfilled") setBingo(bingoResult.value.data);
      if (cerberusResult.status === "rejected" && bingoResult.status === "rejected") {
        setLiveFeedError("Live game feeds are unavailable right now.");
      } else {
        setLiveFeedError(null);
      }
    });
  }, []);

  useEffect(() => {
    loadLiveFeeds();
    const interval = setInterval(loadLiveFeeds, 5000);
    return () => clearInterval(interval);
  }, [loadLiveFeeds]);

  const join = async (g) => {
    if (!user) return loginDiscord();
    setBusy((b) => ({ ...b, [g.id]: true }));
    try {
      await api.post("/games/join", { game_id: g.id, choice: choice[g.id] ?? null });
      setToast({ kind: "ok", msg: `Joined "${g.title}"` });
      await refresh();
    } catch (e) {
      setToast({ kind: "err", msg: describeApiError(e, "Failed to join the game.") });
    } finally {
      setBusy((b) => ({ ...b, [g.id]: false }));
      setTimeout(() => setToast(null), 4000);
    }
  };

  return (
    <section data-testid={GAMES.root} className="bg-[#0a0a0a] text-[#e8e4d9] min-h-screen py-10 px-4 sm:px-6 pb-24">
      <div className="code-sequence max-w-[1400px] mx-auto">
        <div className="chip chip-red mb-2">LIVE ARENA</div>
        <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight">
          Stream <span className="text-[#da291c]">Games</span>
        </h1>
        <p className="font-inter opacity-80 mt-3 max-w-xl">
          Bonus Hunt, Tournament, Chat vs Streamer, Climb the Ladder, and Bonus Bingo.
          Free to enter, with each round managed from the shogun&apos;s console.
        </p>

        <div className="mt-8 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="brutal-border-ivory bg-black p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-anton uppercase text-2xl">Inferno Games · Live Feed</h2>
              <span className={`chip ${cerberus?.games?.length ? "chip-red" : ""}`}>
                {cerberus?.games?.length ? "LIVE" : "STANDBY"}
              </span>
            </div>
            {cerberus?.games?.length ? cerberus.games.map((game) => (
              <div key={game.gameId} className="mt-4 border-t-2 border-[#e8e4d9]/20 pt-4">
                <div className="flex items-center justify-between font-mono text-xs uppercase">
                  <span>{game.status} · {game.phase}</span>
                  <span>{game.participants.length}/{game.maxPlayers} tributes</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {game.participants.map((participant) => (
                    <div key={`${game.gameId}-${participant.displayName}`} className={`border-2 px-2 py-2 font-mono text-xs ${participant.alive ? "border-[#9ed6a5]" : "border-[#da291c]/60 opacity-60"}`}>
                      <div className="truncate">{participant.displayName}</div>
                      <div className="mt-1 opacity-60">{participant.alive ? "ALIVE" : "OUT"} · {participant.kills} K</div>
                    </div>
                  ))}
                </div>
              </div>
            )) : (
              <p className="mt-4 font-mono text-xs opacity-70">
                {cerberus?.error === "not_configured"
                  ? "The Cerberus read bridge is not configured yet."
                  : cerberus?.stale
                    ? "Cerberus is temporarily unreachable; the last known state is marked stale."
                    : "No active Inferno Game is running."}
              </p>
            )}
            {cerberus?.stale && <div className="mt-3 font-mono text-[10px] uppercase text-[#f4c95d]">STALE FEED · {new Date(cerberus.updated_at || Date.now()).toLocaleTimeString()}</div>}
          </div>

          <div className="brutal-border-ivory bg-[#e8e4d9] text-black p-5">
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-anton uppercase text-2xl">Bonus Bingo · Live</h2>
              <span className={`chip ${bingo?.game ? "chip-red" : ""}`}>{bingo?.game?.status || "STANDBY"}</span>
            </div>
            {bingo?.game ? (
              <>
                <p className="mt-3 font-inter text-sm opacity-80">{bingo.game.title}</p>
                <div className="mt-4 grid gap-1" style={{ gridTemplateColumns: `repeat(${bingo.game.gridSize}, minmax(0, 1fr))` }}>
                  {bingo.game.cells.map((cell) => (
                    <div
                      key={cell.id}
                      className={`aspect-square border-2 p-1 text-[9px] leading-tight flex items-center justify-center text-center ${
                        cell.status === "GREEN" ? "border-[#16803c] bg-[#9ed6a5]" :
                          cell.status === "ACTIVE" ? "border-[#da291c] bg-[#f4c95d]" : "border-black/20 bg-white"
                      }`}
                    >
                      {cell.status === "GREEN" ? cell.claimedByChatUsername : cell.slotName || ""}
                    </div>
                  ))}
                </div>
                <div className="mt-4 border-t-2 border-black/15 pt-3 font-mono text-xs">
                  <div className="uppercase">Join from stream chat</div>
                  <div className="mt-1">Type <strong>{bingo.game.keyword}</strong> on Kick or Twitch{bingo.game.status === "ACTIVE" ? " · board is live" : " · registration is open"}.</div>
                  {bingo.game.currentChatUsername && <div className="mt-2 text-[#da291c]">Current draw: <strong>{bingo.game.currentChatUsername}</strong></div>}
                  {bingo.game.participants.length > 0 && (
                    <div className="mt-2 opacity-70">
                      {bingo.game.participants.length} viewers joined · {bingo.game.participants.slice(0, 6).map((participant) => participant.chatUsername).join(", ")}
                      {bingo.game.participants.length > 6 ? "…" : ""}
                    </div>
                  )}
                  {bingo.game.updatedAt && <div className="mt-2 opacity-50">Updated {new Date(bingo.game.updatedAt).toLocaleTimeString()}</div>}
                </div>
              </>
            ) : (
              <p className="mt-4 font-mono text-xs opacity-70">
                {bingo?.error === "not_configured"
                  ? "The reference Bingo feed is not configured yet."
                  : "No Bingo round is active. Check back when the stream is live."}
              </p>
            )}
          </div>
        </div>
        {liveFeedError && <div role="status" className="mt-3 font-mono text-xs text-[#f4c95d]">{liveFeedError}</div>}

        <div className="mt-5 brutal-border bg-[#e8e4d9] text-black p-4 font-mono text-xs">
          <strong className="uppercase">How to join:</strong>{" "}
          Web-managed games use Discord login and the Join button below. Inferno Games are joined through the live Discord game panel after the host runs <code>/hungergames new</code>. Bingo is joined in Kick/Twitch chat with the keyword shown on the live board.
        </div>

        {loadError ? (
          <div role="alert" className="mt-10 brutal-border-ivory bg-[#da291c] text-[#efe9dc] p-6 font-mono text-sm">
            <div>{loadError}</div>
            <button type="button" onClick={() => load({ fresh: true })} className="mt-3 border-2 border-[#efe9dc] px-3 py-1 uppercase">
              Retry
            </button>
          </div>
        ) : loading ? (
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
                  <span>{g.entry_cost > 0 ? `Entry: ${g.entry_cost} pts` : "Free entry"}</span>
                  <span>{g.reward_pool > 0 ? `Pool: ${g.reward_pool} pts` : "Template round"}</span>
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
