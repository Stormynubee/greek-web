import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";

/**
 * Stream-games control panel for the main site.
 *
 * Talks directly to the greek-bingo backend (which owns the Kick/Twitch chat
 * listeners). Authentication is a moderator/admin Discord login against the
 * greek-bingo backend; the access token lives in sessionStorage keyed to this
 * panel and is sent as `Authorization: Bearer <token>`.
 *
 * CORS is already allowed for https://www.greekgambles.com by the bingo backend.
 */

const BINGO_API_BASE =
  (process.env.REACT_APP_BINGO_API_URL || "https://greek-bingo.onrender.com").replace(/\/+$/, "");
const TOKEN_KEY = "ggb_bingo_access_token";
const STREAM_GAME_SLUGS = {
  "Chat vs Streamer": "chat-vs-streamer",
  "Climb the Ladder": "climb-the-ladder",
  "Bonus Bingo": "bonus-bingo",
  "Bonus Hunt": "bonus-hunt",
  Tournament: "tournament",
};

function useBingoAuth() {
  // Read any token in the URL synchronously during the very first render, so
  // the Discord callback's access_token is captured before App.js's AuthFeedback
  // effect rewrites the location.
  const [initial] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    const access = params.get("access_token");
    const refresh = params.get("refresh_token");
    const oauthError = params.get("error");
    const isAdmin = params.get("is_admin") === "true";
    const isMod = params.get("is_moderator") === "true";
    const displayName = params.get("display_name");
    if (access) {
      sessionStorage.setItem(TOKEN_KEY, access);
      if (refresh) sessionStorage.setItem("ggb_bingo_refresh_token", refresh);
      // Clean the URL so the token isn't left in history.
      window.history.replaceState(
        {},
        "",
        window.location.pathname +
          window.location.search
            .replace(/[?&](access_token|refresh_token|user_id|display_name|is_admin|is_moderator|avatar)=[^&]*/g, "")
            .replace(/^&/, "?")
      );
      return { authed: true, user: { displayName, isAdmin, isModerator: isMod }, error: null };
    }
    if (oauthError) {
      // The bingo callback redirected back with an error (e.g. failed exchange).
      // Clear the param so it doesn't keep reappearing, and surface it below.
      window.history.replaceState(
        {},
        "",
        window.location.pathname +
          window.location.search.replace(/[?&]error=[^&]*/g, "").replace(/^&/, "?")
      );
      return { authed: false, user: null, error: oauthError };
    }
    const stored = sessionStorage.getItem(TOKEN_KEY);
    return stored ? { authed: true, user: null, error: null } : { authed: false, user: null, error: null };
  });
  const [authState, setAuthState] = useState(initial.authed ? "authed" : "idle");
  const [error, setError] = useState(initial.error || null);
  const [user, setUser] = useState(initial.user || null);

  const login = useCallback(async () => {
    setAuthState("loggingIn");
    setError(null);
    try {
      // Warm up Render's cold start so the actual initiate doesn't time out.
      try {
        await axios.get(`${BINGO_API_BASE}/health`, { timeout: 45000 });
      } catch {
        /* ignore warm-up failure; initiate will surface the real error */
      }
      const r = await axios.get(`${BINGO_API_BASE}/api/auth/discord/initiate`, {
        params: { redirect: `${window.location.origin}/admin` },
        timeout: 60000,
      });
      const url = r.data?.authUrl;
      if (url) {
        window.location.assign(url);
        return;
      }
      setError("Bingo backend did not return a login URL.");
      setAuthState("error");
    } catch (e) {
      setError(`Could not reach the bingo backend: ${e?.response?.data?.error || e.message}`);
      setAuthState("error");
    }
  }, []);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem("ggb_bingo_refresh_token");
    setAuthState("idle");
    setUser(null);
  }, []);

  return { authState, error, login, logout, token: sessionStorage.getItem(TOKEN_KEY), user };
}

function useBingoApi(token) {
  const call = useCallback(
    async (method, path, body) => {
      const headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const r = await axios({ method, url: `${BINGO_API_BASE}${path}`, data: body, headers, timeout: 60000, withCredentials: true });
      return r.data;
    },
    [token]
  );
  return { call };
}

export default function StreamGamesControl() {
  const { authState, error, login, logout, token, user } = useBingoAuth();
  const { call } = useBingoApi(token);
  const [slug, setSlug] = useState("chat-vs-streamer");
  const [bingoGameId, setBingoGameId] = useState("");
  const [bingoKeyword, setBingoKeyword] = useState("");
  const [slotName, setSlotName] = useState("");
  const [won, setWon] = useState(true);
  const [chatUsername, setChatUsername] = useState("");
  const [preferredSlot, setPreferredSlot] = useState("");
  const [busy, setBusy] = useState(false);
  const [panelMsg, setPanelMsg] = useState(null);
  const [active, setActive] = useState(null);
  const pollRef = useRef(null);

  const flash = (kind, text) => {
    setPanelMsg({ kind, text });
    window.setTimeout(() => setPanelMsg(null), 5000);
  };

  const refreshActive = useCallback(async () => {
    if (!token) return;
    try {
      let payload;
      if (slug === "chat-vs-streamer") {
        const r = await call("get", `/api/predictions/games/${slug}/active`);
        payload = r.match || null;
      } else if (slug === "climb-the-ladder") {
        const r = await call("get", `/api/ladder/games/${slug}/active`);
        payload = r.run || null;
      } else if (slug === "bonus-hunt") {
        const r = await call("get", `/api/hunts/live`);
        payload = r.hunt || null;
      } else if (slug === "tournament") {
        const r = await call("get", `/api/tournaments`);
        const list = Array.isArray(r.tournaments) ? r.tournaments : Array.isArray(r) ? r : [];
        payload = list.find?.((t) => t.status === "ACTIVE" || t.status === "REGISTRATION" || t.status === "SLOT_SELECTION") || null;
      } else {
        const r = await call("get", `/api/bingo/games/${slug}/active`);
        payload = r.game || null;
      }
      setActive(payload);
    } catch {
      /* keep last state */
    }
  }, [call, slug, token]);

  const predMatchId = () => active?.id || active?.matchId || "";
  const predRoundId = () =>
    active?.rounds?.find?.((r) => r.status === "OPEN" || r.status === "LOCKED")?.id ||
    active?.currentRoundId ||
    "";

  useEffect(() => {
    if (authState !== "authed") return;
    refreshActive();
    pollRef.current = setInterval(refreshActive, 10000);
    return () => clearInterval(pollRef.current);
  }, [authState, refreshActive]);

  const run = async (path, body, okText) => {
    setBusy(true);
    try {
      const r = await call("post", path, body);
      flash("ok", okText);
      await refreshActive();
      return r;
    } catch (e) {
      flash("err", `Error: ${e?.response?.data?.error || e.message}`);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const activeId = active?.id;
  const bingoGameActive = active && (active.status === "ACTIVE" || active.status === "REGISTRATION" || active.status === "DRAFT");

  return (
    <div className="space-y-6">
      {panelMsg && (
        <div className={`brutal-border p-3 font-mono text-sm ${panelMsg.kind === "ok" ? "bg-[#efe9dc] text-black" : "bg-[#da291c] text-[#efe9dc]"}`}>
          {panelMsg.text}
        </div>
      )}

      {authState !== "authed" ? (
        <div className="brutal-border-ivory bg-black p-6">
          <h2 className="font-anton uppercase text-2xl">Stream Games Control</h2>
          <p className="font-inter text-sm mt-2 opacity-80">
            Connect your Discord to run the Kick/Twitch stream games from here. Requires moderator/admin access on the bingo backend.
          </p>
          {error && <div className="mt-3 font-mono text-sm text-[#da291c]">{error}</div>}
          <button
            type="button"
            disabled={authState === "loggingIn"}
            onClick={login}
            className="mt-4 font-anton uppercase text-lg py-2 px-4 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50"
          >
            {authState === "loggingIn" ? "Connecting…" : "Connect Discord"}
          </button>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 brutal-border-ivory bg-black p-4">
            <div className="flex flex-wrap items-center gap-2">
              <label className="font-mono text-xs uppercase opacity-70">Game</label>
              <select
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="brutal-border bg-[#efe9dc] text-black p-2 font-mono"
              >
                {Object.entries(STREAM_GAME_SLUGS).map(([label, s]) => (
                  <option key={s} value={s}>{label}</option>
                ))}
              </select>
              <span className={`chip ${active?.status === "ACTIVE" ? "chip-red" : ""}`}>
                {active?.status || "no active round"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              {user?.displayName && (
                <span className="font-mono text-xs opacity-70">
                  {user.displayName} · {user.isAdmin ? "admin" : user.isModerator ? "mod" : "viewer"}
                </span>
              )}
              <button type="button" onClick={refreshActive} className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc]">Refresh</button>
              <button type="button" onClick={logout} className="font-mono text-xs uppercase px-3 py-1 border-2 border-[#efe9dc]/50 opacity-70">Disconnect</button>
            </div>
          </div>

          {/* Quick status of the currently-active bingo game */}
          {bingoGameActive && (
            <div className="brutal-border-ivory bg-black p-4 font-mono text-sm">
              <div className="uppercase text-xs opacity-70">Active {slug} round</div>
              <div className="mt-2 grid sm:grid-cols-2 gap-2 text-xs">
                <div>Title: <strong>{active.title}</strong></div>
                <div>Status: <strong>{active.status}</strong></div>
                {active.keyword && <div>Keyword: <strong>{active.keyword}</strong></div>}
                {active.gridSize && <div>Grid: <strong>{active.gridSize}×{active.gridSize}</strong></div>}
                {typeof active.participants?.length === "number" && <div>Participants: <strong>{active.participants.length}</strong></div>}
                {active.currentChatUsername && <div>Current draw: <strong>{active.currentChatUsername}</strong></div>}
              </div>
            </div>
          )}

          {/* Chat vs Streamer */}
          {slug === "chat-vs-streamer" && (
            <div className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-4">
              <div>
                <h3 className="font-anton uppercase text-xl">Match</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" disabled={busy} onClick={() => run(`/api/predictions/games/${slug}/matches`, {}, "Match created")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Create Match</button>
                  <button type="button" disabled={busy || !predMatchId()} onClick={() => run(`/api/predictions/matches/${predMatchId()}/end`, {}, "Match ended")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">End Match</button>
                </div>
                <div className="mt-4">
                  <input value={bingoKeyword} onChange={(e) => setBingoKeyword(e.target.value)} placeholder="Challenge text (optional)" className="brutal-border bg-[#efe9dc] text-black p-2 w-full font-mono" />
                  <button type="button" disabled={busy || !predMatchId()} onClick={() => run(`/api/predictions/matches/${predMatchId()}/challenge`, { challengeText: bingoKeyword || null }, "Challenge set")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50 mt-2">Set Challenge</button>
                </div>
              </div>
              <div>
                <h3 className="font-anton uppercase text-xl">Round</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" disabled={busy || !predMatchId()} onClick={() => run(`/api/predictions/matches/${predMatchId()}/rounds`, { question: bingoKeyword || "Round", streamerCall: "streamer" }, "Round opened")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Open Round</button>
                  <button type="button" disabled={busy || !predRoundId()} onClick={() => run(`/api/predictions/rounds/${predRoundId()}/lock`, {}, "Round locked")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Lock Round</button>
                </div>
                <div className="mt-4">
                  <select value={won ? "chat" : "streamer"} onChange={(e) => setWon(e.target.value === "chat")} className="brutal-border bg-[#efe9dc] text-black p-2 font-mono w-full">
                    <option value="chat">Chat correct</option>
                    <option value="streamer">Streamer correct</option>
                  </select>
                  <button type="button" disabled={busy || !predRoundId()} onClick={() => run(`/api/predictions/rounds/${predRoundId()}/resolve`, { streamerCorrect: !won }, "Round resolved")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50 mt-2">Resolve Round</button>
                </div>
              </div>
            </div>
          )}

          {/* Bonus Bingo */}
          {slug === "bonus-bingo" && (
            <div className="brutal-border-ivory bg-black p-6 grid md:grid-cols-2 gap-4">
              <div>
                <h3 className="font-anton uppercase text-xl">Create / Setup</h3>
                <div className="mt-3 grid gap-2">
                  <input value={bingoKeyword} onChange={(e) => setBingoKeyword(e.target.value)} placeholder="Title (e.g. Weekend Bingo)" className="brutal-border bg-[#efe9dc] text-black p-2 font-mono" />
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/games/${slug}`, { title: bingoKeyword || "Bonus Bingo" }, "Bingo game created")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Create Game</button>
                  <input value={bingoGameId} onChange={(e) => setBingoGameId(e.target.value)} placeholder="Game ID (shown above, optional)" className="brutal-border bg-[#efe9dc] text-black p-2 font-mono" />
                  <input value={bingoKeyword} onChange={(e) => setBingoKeyword(e.target.value)} placeholder="Keyword (e.g. !join)" className="brutal-border bg-[#efe9dc] text-black p-2 font-mono" />
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/keyword`, { keyword: bingoKeyword }, "Keyword set")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Set Keyword</button>
                </div>
              </div>
              <div>
                <h3 className="font-anton uppercase text-xl">Run</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/open-registration`, {}, "Registration opened")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Open Registration</button>
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/start`, {}, "Game started")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Start Game</button>
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/spin-cell`, {}, "Cell spun")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Spin Cell</button>
                  <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/draw-player`, {}, "Player drawn")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Draw Player</button>
                </div>
                <div className="mt-4 grid gap-2">
                  <div className="flex gap-2">
                    <input value={slotName} onChange={(e) => setSlotName(e.target.value)} placeholder="Slot name" className="brutal-border bg-[#efe9dc] text-black p-2 font-mono flex-1" />
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/cells/${active?.currentCellId || ""}/slot`, { slotName }, "Slot set")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Set Slot</button>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/result`, { won: true }, "Marked WIN")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Mark Win</button>
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/result`, { won: false }, "Marked LOSS")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Mark Loss</button>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/complete`, {}, "Game completed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Complete</button>
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/unlive`, {}, "Unlived")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Unlive</button>
                    <button type="button" disabled={busy} onClick={() => run(`/api/bingo/${bingoGameId || activeId}/cancel`, {}, "Cancelled")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Cancel</button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Climb the Ladder */}
          {slug === "climb-the-ladder" && (
            <div className="brutal-border-ivory bg-black p-6">
              <h3 className="font-anton uppercase text-xl">Climb the Ladder</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={busy} onClick={() => run(`/api/ladder/games/${slug}/runs`, {}, "Ladder run created")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Create Run</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/ladder/runs/${active?.id || ""}/pass`, {}, "Passed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Pass</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/ladder/runs/${active?.id || ""}/fail`, {}, "Failed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Fail</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/ladder/runs/${active?.id || ""}/cashout`, {}, "Cashed out")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Cash Out</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/ladder/runs/${active?.id || ""}/climb`, {}, "Climbed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Climb</button>
              </div>
            </div>
          )}

          {/* Bonus Hunt */}
          {slug === "bonus-hunt" && (
            <div className="brutal-border-ivory bg-black p-6">
              <h3 className="font-anton uppercase text-xl">Bonus Hunt</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={busy} onClick={() => run(`/api/hunts`, { title: "Bonus Hunt" }, "Hunt created")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Create Hunt</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/hunts/${active?.id || ""}/start`, {}, "Hunt started")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Start Hunt</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/hunts/${active?.id || ""}/guessing/open`, {}, "Guessing opened")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Open Guessing</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/hunts/${active?.id || ""}/guessing/close`, {}, "Guessing closed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Close Guessing</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/hunts/${active?.id || ""}/complete`, {}, "Hunt completed")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Complete</button>
              </div>
            </div>
          )}

          {/* Tournament */}
          {slug === "tournament" && (
            <div className="brutal-border-ivory bg-black p-6">
              <h3 className="font-anton uppercase text-xl">Tournament <span className="text-xs opacity-60">(admin only)</span></h3>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={busy} onClick={() => run(`/api/tournaments`, { title: "Tournament" }, "Tournament created")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Create</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/tournaments/${active?.id || ""}/open-registration`, {}, "Registration opened")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Open Registration</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/tournaments/${active?.id || ""}/start`, {}, "Tournament started")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Start</button>
                <button type="button" disabled={busy} onClick={() => run(`/api/tournaments/${active?.id || ""}/cancel`, {}, "Tournament cancelled")} className="font-anton uppercase text-sm py-2 px-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover disabled:opacity-50">Cancel</button>
              </div>
            </div>
          )}

          <p className="font-mono text-xs opacity-60">
            Connected to <strong>{BINGO_API_BASE}</strong>. Commands sent to Kick/Twitch chat are handled by the bingo backend&apos;s chat listeners the moment a round is open.
          </p>
        </>
      )}
    </div>
  );
}
