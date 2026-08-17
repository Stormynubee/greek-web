import { Link } from "react-router-dom";

/**
 * Vertical brutal cards à la Dribbble "Japanese History".
 * Each card has a header meta strip (M1 ▶, M2 ▶, M3 ▶), an image well
 * with a red circular badge, and a bottom title + category tag.
 */
const CARDS = [
  {
    idx: "M1",
    kanji: "目",
    title: "LEADERBOARDS",
    subtitle: "The Rankings",
    tag: "(WAGER-BASED)",
    body: "Live wagers under code GREEK33. Podium ceremony + dense samurai table.",
    accent: "#da291c",
    to: "/leaderboards",
    bg: "#efe9dc",
    fg: "#0a0a0a",
    imageBg: "#0a0a0a",
    imageEl: (
      <>
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="font-anton uppercase text-[#efe9dc] text-[28vw] md:text-[8rem] leading-none opacity-90 select-none">1st</div>
        </div>
        <div className="absolute top-3 right-3 font-mono text-xs text-[#efe9dc]/70 uppercase">$338k · wagered</div>
      </>
    ),
  },
  {
    idx: "M2",
    kanji: "頭",
    title: "THE STORE",
    subtitle: "Trade Points",
    tag: "(REDEMPTION)",
    body: "Turn earned points into stickers, VIP roles, shoutouts and gift cards.",
    accent: "#0a0a0a",
    to: "/store",
    bg: "#0a0a0a",
    fg: "#efe9dc",
    imageBg: "#efe9dc",
    imageEl: (
      <img src="/assets/samurai-coin.png" alt="" className="w-full h-full object-contain p-8" />
    ),
  },
  {
    idx: "M3",
    kanji: "戦",
    title: "STREAM GAMES",
    subtitle: "Predictions · Quizzes",
    tag: "(LIVE ARENA)",
    body: "Predict outcomes, join raffles, answer quizzes during the streams — win points.",
    accent: "#da291c",
    to: "/stream-games",
    bg: "#efe9dc",
    fg: "#0a0a0a",
    imageBg: "#0a0a0a",
    imageEl: (
      <>
        <div className="absolute inset-0 grid grid-cols-6 grid-rows-6 pointer-events-none">
          {Array.from({ length: 36 }).map((_, i) => (
            <div key={i} className="border border-[#efe9dc]/10" />
          ))}
        </div>
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-[#efe9dc]">
          <div className="font-anton text-4xl">?</div>
          <div className="font-mono text-xs opacity-70">PREDICT · WIN · REPEAT</div>
        </div>
        <div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-1 bg-[#da291c]/60" />
      </>
    ),
  },
];

export default function FeatureCards() {
  return (
    <section className="bg-[#efe9dc] py-16 px-4 sm:px-6 border-t-4 border-black">
      <div className="max-w-[1400px] mx-auto">
        <div className="flex items-baseline justify-between mb-8 gap-4 flex-wrap">
          <h2 className="font-anton uppercase text-4xl sm:text-6xl leading-none tracking-tight text-black">
            The <span className="text-[#da291c]">Codex</span> · Three Paths
          </h2>
          <div className="flex items-center gap-2 font-mono text-xs uppercase opacity-70">
            <span>◈ scroll</span>
            <span>▼</span>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {CARDS.map((c) => (
            <Link
              key={c.idx}
              to={c.to}
              className="brutal-border brutal-shadow brutal-hover flex flex-col overflow-hidden"
              style={{ background: c.bg, color: c.fg }}
            >
              {/* Header strip */}
              <div className="flex items-center justify-between px-3 py-2 border-b-2 font-mono text-xs uppercase" style={{ borderColor: c.fg + "22" }}>
                <div className="flex items-center gap-2">
                  <span className="chip">{`(${c.kanji})`}</span>
                  <span>0 / {c.idx} ▶</span>
                </div>
                <span className="w-3 h-3 rounded-full" style={{ background: c.accent }} />
              </div>

              {/* Image well */}
              <div className="relative aspect-[4/5] w-full overflow-hidden" style={{ background: c.imageBg }}>
                {c.imageEl}
                <div className="absolute top-3 left-3 chip chip-red text-[10px]">RESTORATION IN PROGRESS</div>
              </div>

              {/* Body */}
              <div className="p-4 border-t-2" style={{ borderColor: c.fg + "22" }}>
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="font-anton uppercase text-2xl leading-none tracking-tight">{c.title}</h3>
                  <span className="font-mono text-[10px] uppercase" style={{ color: c.accent }}>{c.tag}</span>
                </div>
                <div className="font-mono text-xs uppercase mt-1 opacity-80">{c.subtitle}</div>
                <p className="font-inter text-sm mt-3 leading-relaxed opacity-90">{c.body}</p>
                <div className="mt-4 font-anton uppercase text-base flex items-center gap-2">
                  Enter <span aria-hidden>→</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
