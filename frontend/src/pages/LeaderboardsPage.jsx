import { useEffect, useState, useCallback, useRef } from "react";
import { api, describeApiError } from "@/lib/api";
import { LEADERBOARD } from "@/constants/testIds";
import TransparentVideo from "@/components/TransparentVideo";

const TABS = [
  { key: "daily",   label: "Daily",   tid: LEADERBOARD.tabDaily },
  { key: "weekly",  label: "Weekly",  tid: LEADERBOARD.tabWeekly },
  { key: "monthly", label: "Monthly", tid: LEADERBOARD.tabMonthly },
];

const fmt = (n) => new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n);

export default function LeaderboardsPage() {
  const [type, setType] = useState("monthly");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [ghostEdge, setGhostEdge] = useState(null);
  const requestSequence = useRef(0);
  const requestController = useRef(null);
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const load = useCallback(async (kind, { fresh = false } = {}) => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setLoading(true); setError(null);
    try {
      const r = await api.get("/leaderboard", {
        params: {
          type: kind,
          mask: false,
          ...(fresh ? { _refresh: Date.now() } : {}),
        },
        signal: controller.signal,
      });
      if (sequence === requestSequence.current) setData(r.data);
    } catch (e) {
      if (e?.code !== "ERR_CANCELED" && sequence === requestSequence.current) {
        setError(describeApiError(e, "Could not load the leaderboard."));
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(type);
    return () => requestController.current?.abort();
  }, [type, load]);

  const rankings = data?.rankings || [];
  const podium = rankings.slice(0, 3);
  const rest = rankings.slice(3);
  const ghostDialogue = ghostEdge === "left"
    ? "The left gate cannot hold me."
    : "The right gate bows to the blade.";
  const visitTwitch = () => {
    window.location.assign("https://www.twitch.tv/greekgodberry");
  };

  return (
    <section
      data-testid={LEADERBOARD.root}
      className="relative bg-[#0a0a0a] min-h-screen text-[#e8e4d9] pb-24"
    >
      {/* Transparent animated coin and Samurai Ghost layers */}
      {!reduced && (
        <>
          <TransparentVideo
            data-testid={LEADERBOARD.ghostVideo}
            src="/assets/samurai-coin-greenscreen.mp4"
            className="absolute right-4 top-4 w-[220px] max-w-[35vw] aspect-video pointer-events-none select-none"
            style={{ zIndex: 1, animation: "heroCoinFloat 5s ease-in-out infinite" }}
          />
          <TransparentVideo
            src="/assets/samurai-ghost-walk.mp4"
            motion="ghost"
            interactive
            onEdgeChange={setGhostEdge}
            onClick={visitTwitch}
            ariaLabel="Samurai ghost. Click to visit GreekGodBerry on Twitch."
            className="absolute left-0 bottom-20 w-[min(360px,48vw)] aspect-video select-none"
            style={{ zIndex: 1 }}
          />
          {ghostEdge && (
            <div
              className={`ghost-dialogue ghost-dialogue-${ghostEdge}`}
              role="status"
              aria-live="polite"
            >
              <span>{ghostDialogue}</span>
              <button type="button" onClick={visitTwitch}>Visit Twitch →</button>
            </div>
          )}
        </>
      )}

      <div className="relative max-w-[1400px] mx-auto px-4 sm:px-6 pt-10" style={{ zIndex: 2 }}>
        <div className="chip chip-red mb-3">LEADERBOARDS · CODE GREEK33</div>
        <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight">
          The <span className="text-[#da291c]">Rankings</span>
        </h1>
        <p className="font-inter opacity-80 mt-3 max-w-xl">
          Live wagers via Lockly, cached 60s. UTC boundaries. Names left unmasked as configured.
        </p>
        {data?.upstream_unavailable && (
          <div role="status" className="mt-4 max-w-xl brutal-border p-3 font-mono text-xs text-[#f4c95d]">
            Live wager data is temporarily unavailable. Showing any locally saved rankings.
          </div>
        )}

        {/* Tabs + refresh */}
        <div className="mt-8 flex flex-wrap gap-2 items-center">
          {TABS.map((t) => (
            <button
              key={t.key}
              data-testid={t.tid}
              onClick={() => setType(t.key)}
              className={`font-anton uppercase text-lg px-4 py-2 brutal-border ${
                type === t.key
                  ? "bg-[#da291c] text-[#e8e4d9] brutal-shadow-ivory"
                  : "bg-[#e8e4d9] text-black brutal-shadow brutal-hover"
              }`}
            >
              {t.label}
            </button>
          ))}
          <button
            data-testid={LEADERBOARD.refresh}
            onClick={() => load(type, { fresh: true })}
            className="ml-auto font-mono text-xs uppercase px-3 py-2 border-2 border-[#e8e4d9] hover:bg-[#e8e4d9] hover:text-black transition-colors"
          >
            ↻ Refresh
          </button>
        </div>

        {/* Summary */}
        {data && (
          <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3 font-mono text-sm">
            <div className="brutal-border-ivory p-3 bg-black">
              <div className="text-xs uppercase opacity-60">Type</div>
              <div className="text-lg mt-1">{data.type.toUpperCase()}</div>
            </div>
            <div className="brutal-border-ivory p-3 bg-black">
              <div className="text-xs uppercase opacity-60">Total Users</div>
              <div className="text-lg mt-1">{data.total_users}</div>
            </div>
            <div className="brutal-border-ivory p-3 bg-black">
              <div className="text-xs uppercase opacity-60">Total Wagered</div>
              <div className="text-lg mt-1">${fmt(data.total_wagered)}</div>
            </div>
            <div className="brutal-border-ivory p-3 bg-black">
              <div className="text-xs uppercase opacity-60">Since</div>
              <div className="text-lg mt-1">{data.from ? data.from.slice(0, 10) : "—"}</div>
            </div>
          </div>
        )}

        {/* Podium */}
        {loading && <div className="mt-10 font-mono">LOADING...</div>}
        {error && <div className="mt-10 font-mono text-[#da291c]">{error}</div>}
        {!loading && !error && rankings.length === 0 && (
          <div className="mt-10 font-mono">No entries this period.</div>
        )}
        {!loading && podium.length > 0 && (
          <div data-testid={LEADERBOARD.podium} className="mt-10 grid grid-cols-3 gap-3 sm:gap-6 items-end">
            {[1, 0, 2].map((idx, i) => {
              const p = podium[idx];
              if (!p) return <div key={i} />;
              const height = idx === 0 ? "h-56 sm:h-72" : idx === 1 ? "h-40 sm:h-52" : "h-32 sm:h-40";
              const bg = idx === 0 ? "#da291c" : "#e8e4d9";
              const fg = idx === 0 ? "#e8e4d9" : "#0a0a0a";
              return (
                <div key={i} className="text-center">
                  <div className="font-anton text-4xl sm:text-6xl">{idx === 0 ? "1st" : idx === 1 ? "2nd" : "3rd"}</div>
                  <div className={`mt-3 ${height} brutal-border brutal-shadow flex flex-col items-center justify-center p-3`}
                    style={{ background: bg, color: fg }}>
                    <div className="font-mono text-xs uppercase opacity-80">Wagered</div>
                    <div className="font-anton text-2xl sm:text-4xl mt-1">${fmt(p.wagered)}</div>
                    <div className="font-mono text-sm mt-3 truncate w-full">{p.name}</div>
                    <div className="font-mono text-xs opacity-70">{p.bets} bets</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Table */}
        {!loading && rest.length > 0 && (
          <div data-testid={LEADERBOARD.table} className="mt-10 brutal-border-ivory bg-black overflow-x-auto">
            <table className="w-full font-mono text-sm">
              <thead>
                <tr className="bg-[#e8e4d9] text-black">
                  <th className="text-left px-3 py-2 uppercase text-xs">#</th>
                  <th className="text-left px-3 py-2 uppercase text-xs">Player</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Wagered</th>
                  <th className="text-right px-3 py-2 uppercase text-xs">Bets</th>
                </tr>
              </thead>
              <tbody>
                {rest.map((r) => (
                  <tr key={r.rank} data-testid={LEADERBOARD.row(r.rank)} className="border-t-2 border-[#e8e4d9]/20 hover:bg-[#da291c]/20">
                    <td className="px-3 py-2 font-anton text-lg">{r.rank}</td>
                    <td className="px-3 py-2 truncate max-w-[220px]">{r.name}</td>
                    <td className="px-3 py-2 text-right">${fmt(r.wagered)}</td>
                    <td className="px-3 py-2 text-right opacity-70">{r.bets}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
