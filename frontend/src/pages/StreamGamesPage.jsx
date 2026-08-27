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
  const [liveGames, setLiveGames] = useState(null);
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

  const liveFeedController = useRef(null);
  const liveFeedSequence = useRef(0);
  const liveFeedInterval = useRef(null);

  const loadLiveFeeds = useCallback(() => {
    liveFeedController.current?.abort();
    const controller = new AbortController();
    liveFeedController.current = controller;
    const sequence = liveFeedSequence.current + 1;
    liveFeedSequence.current = sequence;
    Promise.allSettled([
      api.get("/cerberus/live-state", { signal: controller.signal }),
      api.get("/bingo/active", { signal: controller.signal }),
      api.get("/stream-games/live", { signal: controller.signal }),
    ]).then(([cerberusResult, bingoResult, liveResult]) => {
      if (sequence !== liveFeedSequence.current) return;
      if (cerberusResult.status === "fulfilled") setCerberus(cerberusResult.value.data);
      if (bingoResult.status === "fulfilled") setBingo(bingoResult.value.data);
      if (liveResult.status === "fulfilled") setLiveGames(liveResult.value.data);
      const allRejected = [cerberusResult, bingoResult, liveResult].every((r) => r.status === "rejected");
      setLiveFeedError(allRejected ? "Live game feeds are unavailable right now." : null);
    });
  }, []);

  useEffect(() => {
    loadLiveFeeds();
    const schedule = () => {
      const isHidden = typeof document !== "undefined" && document.hidden;
      const bothNotConfigured =
        cerberus?.error === "not_configured" && bingo?.error === "not_configured";
      const delay = isHidden ? 30000 : bothNotConfigured ? 60000 : 5000;
      liveFeedInterval.current = setTimeout(() => {
        loadLiveFeeds();
        schedule();
      }, delay);
    };
    schedule();
    const onVis = () => {
      if (!document.hidden) {
        clearTimeout(liveFeedInterval.current);
        loadLiveFeeds();
        schedule();
      }
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      liveFeedController.current?.abort();
      clearTimeout(liveFeedInterval.current);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [loadLiveFeeds, cerberus?.error, bingo?.error]);

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

        {/* Bingo-backend live games: Chat vs Streamer, Ladder, Bonus Hunt, Tournament */}
        {liveGames?.available && Object.keys(liveGames.games || {}).length > 0 && (
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {liveGames.games.chat_vs_streamer && <ChatVsStreamerPanel game={liveGames.games.chat_vs_streamer} />}
            {liveGames.games.climb_the_ladder && <LadderPanel game={liveGames.games.climb_the_ladder} />}
            {liveGames.games.bonus_hunt && <BonusHuntPanel game={liveGames.games.bonus_hunt} />}
            {liveGames.games.tournament && <TournamentPanel game={liveGames.games.tournament} />}
          </div>
        )}

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

/* ---------- Bingo-backend live game panels ---------- */

function PanelShell({ title, status, accent = false, children }) {
  return (
    <div className={`brutal-border-ivory p-5 ${accent ? "bg-[#da291c] text-[#efe9dc]" : "bg-black text-[#e8e4d9]"}`}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-anton uppercase text-2xl">{title}</h2>
        <span className={`chip ${accent ? "" : "chip-red"}`}>{status}</span>
      </div>
      {children}
    </div>
  );
}

function ChatVsStreamerPanel({ game }) {
  const round = game.currentRound;
  const totalVotes = (round?.votesChat || 0) + (round?.votesStreamer || 0);
  return (
    <PanelShell title="Chat vs Streamer" status={game.status || "LIVE"} accent>
      {game.challengeText && <p className="mt-2 font-inter text-sm opacity-90">{game.challengeText}</p>}
      <div className="mt-4 grid grid-cols-2 gap-3 text-center">
        <div className="brutal-border bg-black/30 p-3">
          <div className="font-anton text-4xl leading-none">{game.chatScore ?? 0}</div>
          <div className="font-mono text-[10px] uppercase mt-1 opacity-80">Chat</div>
        </div>
        <div className="brutal-border bg-black/30 p-3">
          <div className="font-anton text-4xl leading-none">{game.streamerScore ?? 0}</div>
          <div className="font-mono text-[10px] uppercase mt-1 opacity-80">Streamer</div>
        </div>
      </div>
      {game.targetScore ? (
        <div className="mt-2 font-mono text-[10px] uppercase opacity-70">First to {game.targetScore} wins</div>
      ) : null}
      {round && (
        <div className="mt-4 border-t-2 border-white/25 pt-3 font-mono text-xs">
          <div className="flex items-center justify-between uppercase">
            <span>Round {round.roundNumber} · {round.status}</span>
            {round.streamerCorrect !== null && round.streamerCorrect !== undefined && (
              <span className={round.streamerCorrect ? "text-[#9ed6a5]" : "text-[#f4c95d]"}>
                {round.streamerCorrect ? "streamer was right" : "chat wins the round"}
              </span>
            )}
          </div>
          {round.question && <div className="mt-1 opacity-90">{round.question}</div>}
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className="brutal-border border-[#efe9dc] p-2">
              <div className="font-anton text-xl leading-none">{round.votesChat ?? 0}</div>
              <div className="text-[10px] uppercase opacity-80 mt-1">!win chat</div>
            </div>
            <div className="brutal-border border-[#efe9dc] p-2">
              <div className="font-anton text-xl leading-none">{round.votesStreamer ?? 0}</div>
              <div className="text-[10px] uppercase opacity-80 mt-1">!win streamer</div>
            </div>
          </div>
          {round.status === "OPEN" && (
            <div className="mt-2 opacity-75">Vote in chat: <strong>!win chat</strong> or <strong>!win streamer</strong>{totalVotes > 0 ? ` · ${totalVotes} votes` : ""}</div>
          )}
          {round.status === "LOCKED" && <div className="mt-2 text-[#f4c95d]">Voting locked — result incoming…</div>}
        </div>
      )}
      {game.winner && (
        <div className="mt-4 brutal-border border-[#efe9dc] p-2 font-anton uppercase text-center text-lg">
          {game.winner === "CHAT" ? "Chat takes the W" : "Streamer takes the W"}
        </div>
      )}
    </PanelShell>
  );
}

function LadderPanel({ game }) {
  return (
    <PanelShell title="Climb the Ladder" status={game.status || "RUNNING"}>
      <div className="mt-3 font-inter text-sm">
        {game.participantName && <div>Climber: <strong>{game.participantName}</strong></div>}
        {game.currentLevel && (
          <div className="mt-1">Level <strong>{game.currentLevel.level ?? game.currentLevel}</strong>
            {game.finalPoints ? <> · playing for <strong>{game.finalPoints} pts</strong></> : null}
          </div>
        )}
      </div>
      {game.updatedAt && <div className="mt-3 font-mono text-[10px] uppercase opacity-50">Updated {new Date(game.updatedAt).toLocaleTimeString()}</div>}
    </PanelShell>
  );
}

function BonusHuntPanel({ game }) {
  const done = game.completedSlots ?? 0;
  const total = game.totalSlots ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <PanelShell title="Bonus Hunt" status={game.status || "LIVE"}>
      {game.title && <p className="mt-2 font-inter text-sm opacity-90">{game.title}</p>}
      {total > 0 && (
        <>
          <div className="mt-3 h-4 brutal-border bg-black/40 overflow-hidden">
            <div className="h-full bg-[#9ed6a5]" style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1 font-mono text-xs flex justify-between">
            <span>{done}/{total} slots opened</span>
            <span>{pct}%</span>
          </div>
        </>
      )}
      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-xs">
        {game.currentGame && <div>Now: <strong>{game.currentGame}</strong></div>}
        {game.multiplierSum != null && <div>Multipliers: <strong>{game.multiplierSum}x</strong></div>}
        {game.startBalance != null && <div>Start: <strong>{game.startBalance}</strong></div>}
      </div>
    </PanelShell>
  );
}

function TournamentPanel({ game }) {
  return (
    <PanelShell title="Tournament" status={game.status || "LIVE"}>
      {game.title && <p className="mt-2 font-inter text-sm opacity-90">{game.title}</p>}
      <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-xs">
        <div>Round: <strong>{game.currentRound ?? 0}</strong></div>
        <div>Players: <strong>{game.maxPlayers ?? "—"}</strong></div>
        {game.prizeCoins > 0 && <div className="col-span-2">Prize pool: <strong>{game.prizeCoins} coins</strong></div>}
      </div>
      {game.status === "REGISTRATION" && <div className="mt-3 font-mono text-xs opacity-80">Registration open — join from the stream.</div>}
    </PanelShell>
  );
}
// $(Get-Date -Format 'yyyy-MM-dd HH:mm')  
