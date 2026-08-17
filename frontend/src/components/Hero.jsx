import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";
import { HERO } from "@/constants/testIds";
import { api } from "@/lib/api";
import TransparentVideo from "@/components/TransparentVideo";

const SOCIALS = [
  {
    id: HERO.socialDiscord, key: "discord", label: "Discord",
    href: "https://discord.gg/quEGjqWrT", color: "#5865F2",
    svg: (<path d="M20.317 4.369A19.79 19.79 0 0 0 16.558 3l-.257.398a15.87 15.87 0 0 0-4.6 0L11.442 3A19.79 19.79 0 0 0 7.683 4.369C4.6 8.94 3.83 13.38 4.207 17.762c1.93 1.42 3.799 2.28 5.638 2.848l.454-.593a13.35 13.35 0 0 1-2.078-.99c.174-.128.345-.262.51-.4a13.6 13.6 0 0 0 11.538 0c.166.138.336.272.51.4-.667.398-1.363.727-2.078.99l.454.593c1.84-.568 3.708-1.427 5.638-2.848.435-4.988-.696-9.4-3.476-13.393zM9.968 15.331c-1.1 0-2.006-1.006-2.006-2.245 0-1.24.892-2.245 2.006-2.245 1.115 0 2.02 1.006 2.006 2.245 0 1.24-.891 2.245-2.006 2.245zm4.064 0c-1.1 0-2.006-1.006-2.006-2.245 0-1.24.891-2.245 2.006-2.245 1.114 0 2.02 1.006 2.005 2.245 0 1.24-.891 2.245-2.005 2.245z"/>),
  },
  {
    id: HERO.socialTwitch, key: "twitch", label: "Twitch",
    href: "https://www.twitch.tv/greekgodberry", color: "#9146FF",
    svg: (<path d="M4.265 3 3 6.578v14.264h4.844V24h2.828l3.156-3.158h4.109L24 15.107V3H4.265zm2.111 2.111h15.512v9L18.311 18h-5.156l-3.156 3.155V18H6.376V5.111zM11.014 8.267v6.001h2.115v-6h-2.115zm5.732 0v6.001h2.113v-6h-2.113z"/>),
  },
  {
    id: HERO.socialKick, key: "kick", label: "Kick",
    href: "https://kick.com/greekgodberry", color: "#53fc18",
    svg: (<path d="M2 4h5v4h2V6h2V4h5v4h-2v2h-2v4h2v2h2v4h-5v-2H9v-2H7v6H2V4z"/>),
  },
  {
    id: HERO.socialYoutube, key: "youtube", label: "YouTube",
    href: "https://www.youtube.com/@greekgodberry", color: "#FF0000",
    svg: (<path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>),
  },
  {
    id: "hero-social-instagram", key: "instagram", label: "Instagram",
    href: "https://www.instagram.com/greekgodberry/?hl=en", color: "#E1306C",
    svg: (<path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 1 0 0 12.324 6.162 6.162 0 0 0 0-12.324zM12 16a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.406-11.845a1.44 1.44 0 1 0 0 2.881 1.44 1.44 0 0 0 0-2.881z"/>),
  },
  {
    id: HERO.socialX, key: "x", label: "X / Twitter",
    href: "https://x.com/greekgodberryx", color: "#ffffff",
    svg: (<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>),
  },
];

// Official Discord mark for the tile background layer
const DiscordMascot = () => (
  <svg viewBox="0 0 24 24" width="70%" height="70%" aria-hidden>
    <rect x="1" y="1" width="22" height="22" rx="5" fill="#5865F2" />
    <g transform="translate(2.4 2.4) scale(0.8)" fill="#fff">
      {SOCIALS[0].svg}
    </g>
  </svg>
);

const BG_TILES = [
  { top: "8%", left: "8%",  size: 78, rot: -8,  key: "twitch",   delay: "0s" },
  { top: "4%",  left: "84%", size: 72, rot: 6,   key: "kick",     delay: "0.6s" },
  { top: "4%",  left: "48%", size: 60, rot: -12, key: "youtube",  delay: "1.2s" },
  { top: "62%", left: "6%",  size: 88, rot: 10,  key: "discord",  delay: "0.3s" },
  { top: "78%", left: "82%", size: 70, rot: -6,  key: "x",        delay: "0.9s" },
  { top: "48%", left: "88%", size: 60, rot: 14,  key: "instagram",delay: "1.5s" },
  { top: "72%", left: "42%", size: 54, rot: -3,  key: "youtube",  delay: "0.4s" },
  { top: "36%", left: "3%",  size: 66, rot: 8,   key: "instagram",delay: "1.1s" },
];
const socialByKey = Object.fromEntries(SOCIALS.map(s => [s.key, s]));

export default function Hero({ liveStatus }) {
  const { user, loginDiscord } = useAuth();
  const [fetchedLive, setFetchedLive] = useState({ is_live: false });

  useEffect(() => {
    if (liveStatus) return undefined;
    api.get("/live").then(r => setFetchedLive(r.data)).catch(() => {});
    return undefined;
  }, [liveStatus]);

  const live = liveStatus || fetchedLive;

  return (
    <section
      data-testid={HERO.root}
      className="relative w-full overflow-hidden bg-[#efe9dc] text-[#0a0a0a] min-h-[92vh] hero-surface"
      style={{
        backgroundImage:
          "radial-gradient(circle at 25% 15%, rgba(218,41,28,0.05) 0%, transparent 45%), radial-gradient(circle at 80% 85%, rgba(0,0,0,0.06) 0%, transparent 40%)",
      }}
    >
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 flex flex-col text-black/[0.06] select-none pointer-events-none"
        style={{ zIndex: 1 }}
      >
        <div className="font-anton uppercase text-[16vw] leading-[0.85] tracking-tight px-4 mt-2 whitespace-nowrap">
          グリーク・ゴッドベリー
        </div>
      </div>

      <div className="absolute inset-0 pointer-events-auto" style={{ zIndex: 6 }}>
        {BG_TILES.map((t, i) => {
          const s = socialByKey[t.key];
          return (
            <a
              key={i}
              href={s.href}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open GreekGodBerry on ${s.label}`}
              className="absolute brutal-border bg-white flex items-center justify-center brutal-shadow social-tile"
              style={{
                top: t.top, left: t.left, width: `${t.size}px`, height: `${t.size}px`,
                "--r": `${t.rot}deg`,
                animation: `heroDrift 9s ease-in-out ${t.delay} infinite`,
              }}
            >
              {s.key === "discord" ? <DiscordMascot /> : (
                <svg viewBox="0 0 24 24" width="55%" height="55%" fill={s.color} aria-hidden>{s.svg}</svg>
              )}
            </a>
          );
        })}
      </div>

      <div
        aria-hidden
        className="absolute -left-20 top-[36%] w-[130%] h-12 sm:h-16 bg-[#da291c]"
        style={{ transform: "rotate(-4deg)", zIndex: 3, boxShadow: "0 6px 0 0 #000" }}
      />

      <div className="relative max-w-[1400px] mx-auto px-4 sm:px-6 pt-6 pb-24 md:pt-10 grid grid-cols-1 md:grid-cols-3 gap-6" style={{ zIndex: 5 }}>
        {/* Left */}
        <div className="md:pt-8 hero-copy hero-delay-1">
          <div className="flex items-center gap-2 mb-3">
            <span className="chip">{`( 日 本 )`}</span>
            <span className="chip chip-red">SEASON I</span>
            {live?.is_live && (
              <a
                data-testid="hero-live-widget"
                href={live.url || "https://kick.com/greekgodberry"}
                target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-1 chip chip-red animate-pulse"
                style={{ background: "#da291c", color: "#fff" }}
              >
                <span className="w-2 h-2 rounded-full bg-white" />
                LIVE ON {live.platform?.toUpperCase() || "KICK"}
              </a>
            )}
          </div>
          <div className="font-mono code-text text-[11px] uppercase tracking-widest opacity-70">GreekGodBerry — In Streaming</div>
          <p className="font-mono code-text text-sm mt-3 leading-relaxed max-w-xs">
            SAMURAI OF THE <span className="text-[#da291c]">SLOTS</span>. WAGERER OF WORLDS.
            HE STACKS COINS <span className="text-[#da291c]">/</span> BUILDS ARMIES
            UNDER CODE <span className="text-[#da291c]">GREEK33</span>.
          </p>
          <div className="mt-6 flex items-center gap-2 font-mono text-xs opacity-70">
            <span>◈ 0 / M1 ▶</span>
            <span className="opacity-40">◈ 0 / M2 ▶</span>
            <span className="opacity-40">◈ 0 / M3 ▶</span>
          </div>
        </div>

        {/* Center */}
        <div className="relative flex items-center justify-center min-h-[600px] hero-stage">
          <div aria-hidden
            className="hero-circle-outline absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[420px] h-[420px] max-w-[80vw] max-h-[80vw] rounded-full border-[10px] border-black"
            style={{ zIndex: 2, clipPath: "polygon(0 0, 100% 0, 100% 82%, 90% 100%, 0 100%)" }}
          />
          <div aria-hidden
            className="hero-circle-core absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] h-[340px] max-w-[64vw] max-h-[64vw] rounded-full bg-[#da291c]"
            style={{ zIndex: 3 }}
          />
          <div className="hero-portrait-stage relative w-[80%] max-w-[420px]" style={{ zIndex: 4 }}>
            <div className="hero-portrait-interaction">
              <img
                data-testid={HERO.cutout}
                src="/assets/greek-cutout.webp"
                alt="GreekGodBerry"
                loading="eager"
                fetchPriority="high"
                decoding="async"
                width="1500"
                height="2000"
                className="hero-portrait relative w-full object-contain"
                style={{ filter: "drop-shadow(6px 6px 0 rgba(0,0,0,0.85))" }}
              />
            </div>
          </div>
          <TransparentVideo
            data-testid={HERO.coinVideo}
            src="/assets/samurai-coin-greenscreen.mp4"
            className="absolute bottom-4 right-2 md:right-[-30px] w-28 md:w-36 aspect-square object-contain"
            style={{ zIndex: 6, animation: "heroCoinFloat 4s ease-in-out infinite" }}
          />
        </div>

        {/* Right */}
        <div className="md:pt-4 flex flex-col hero-copy hero-delay-2">
          <h1
            data-testid={HERO.headline}
            className="font-anton code-text uppercase text-6xl sm:text-7xl md:text-[86px] leading-[0.85] tracking-tight text-black"
          >
            <span className="block text-[#0a0a0a]">GREEK</span>
            <span className="block"><span className="text-[#da291c]">GOD</span><span className="text-[#0a0a0a]">BERRY</span></span>
          </h1>
          <div className="code-text mt-4 font-mono text-xs uppercase tracking-widest">
            <div className="flex items-center justify-between border-t-2 border-black py-1">
              <span>ORIGIN</span><span className="opacity-60">/ streamer</span>
            </div>
            <div className="flex items-center justify-between border-t-2 border-black py-1">
              <span>CODE</span><span className="text-[#da291c] font-bold">GREEK33</span>
            </div>
            <div className="flex items-center justify-between border-t-2 border-black border-b-2 py-1">
              <span>PATH</span><span className="opacity-60">wagers &amp; wisdom</span>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            {!user && (
              <button
                data-testid={HERO.ctaJoin}
                onClick={loginDiscord}
                className="font-anton code-text uppercase text-xl px-5 py-3 bg-black text-[#efe9dc] brutal-border brutal-shadow-red brutal-hover button-feedback"
              >
                Join with Discord →
              </button>
            )}
            <Link
              data-testid={HERO.ctaLeaderboard}
              to="/leaderboards"
              className="font-anton code-text uppercase text-xl px-5 py-3 bg-[#da291c] text-[#efe9dc] brutal-border brutal-shadow brutal-hover inline-block button-feedback"
            >
              See Rankings
            </Link>
          </div>

          <ul className="mt-6 flex flex-wrap gap-2 hero-social-row">
            {SOCIALS.map((s) => (
              <li key={s.key}>
                <a
                  data-testid={s.id}
                  href={s.href} target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-2 chip hover:!bg-black hover:!text-[#efe9dc] transition-colors"
                >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">{s.svg}</svg>
                  {s.label} ↗
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="relative border-y-4 border-black bg-black text-[#efe9dc] hero-stats" style={{ zIndex: 8 }}>
        <div className="code-sequence max-w-[1400px] mx-auto grid grid-cols-2 md:grid-cols-4 divide-x-2 divide-[#da291c]">
          {[
            { k: "スシ // Season", v: "I" },
            { k: "コード // Code", v: "GREEK33" },
            { k: "ライブ // Live", v: live?.is_live ? "ON AIR" : "24/7" },
            { k: "気分 // Vibes", v: "MAX" },
          ].map((s) => (
            <div key={s.k} className="px-4 py-4 flex items-baseline justify-between">
              <span className="font-mono text-[10px] uppercase opacity-70">{s.k}</span>
              <span className="font-anton text-2xl md:text-3xl">{s.v}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
