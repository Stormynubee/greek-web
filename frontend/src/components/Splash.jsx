import { useEffect, useState } from "react";
import { SPLASH } from "@/constants/testIds";

/**
 * Real-asset loader splash screen.
 * Preloads a list of critical assets (images/videos) then reveals the site.
 * Skips itself on repeat visits (localStorage), respects prefers-reduced-motion.
 */
const ASSETS = [
  { url: "/assets/greek-cutout.webp", kind: "image" },
  { url: "/assets/samurai-coin.png", kind: "image" },
  { url: "/assets/paw-cursor.png", kind: "image" },
  { url: "/assets/samurai-coin.webm", kind: "video" },
  { url: "/assets/ghost.webm", kind: "video" },
];

const preloadOne = (a) =>
  new Promise((resolve) => {
    if (a.kind === "image") {
      const img = new Image();
      img.onload = img.onerror = () => resolve();
      img.src = a.url;
    } else {
      fetch(a.url).then(() => resolve()).catch(() => resolve());
    }
  });

export default function Splash({ onDone }) {
  const [pct, setPct] = useState(0);
  const [ready, setReady] = useState(false);
  const [showSkip, setShowSkip] = useState(false);
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    try {
      if (localStorage.getItem("ggb_splash_seen") === "1") {
        onDone?.();
        return;
      }
    } catch { /* localStorage unavailable */ }

    let cancelled = false;
    const start = performance.now();
    let done = 0;

    const failsafe = setTimeout(() => {
      if (!cancelled) { setPct(100); setReady(true); }
    }, 8000);
    const skipTimer = setTimeout(() => setShowSkip(true), 2000);

    Promise.all(
      ASSETS.map((a) =>
        preloadOne(a).then(() => {
          done += 1;
          if (!cancelled) setPct(Math.round((done / ASSETS.length) * 100));
        })
      )
    ).then(() => {
      if (cancelled) return;
      const elapsed = performance.now() - start;
      const wait = reduced ? 0 : Math.max(0, 900 - elapsed);
      setTimeout(() => { setPct(100); setReady(true); }, wait);
    });

    return () => {
      cancelled = true;
      clearTimeout(failsafe);
      clearTimeout(skipTimer);
    };
  }, [onDone, reduced]);

  const enter = () => {
    try { localStorage.setItem("ggb_splash_seen", "1"); } catch { /* noop */ }
    onDone?.();
  };

  // 3 coin positions (top center, mid-left, mid-right) — pixel samurai coins
  const coins = [
    { top: "10%", left: "50%", size: 130, delay: "0s", rot: -6 },
    { top: "42%", left: "12%", size: 110, delay: "0.4s", rot: 8 },
    { top: "42%", left: "88%", size: 110, delay: "0.8s", rot: -10 },
  ];

  return (
    <div
      data-testid={SPLASH.root}
      className="fixed inset-0 z-[100] bg-[#0a0a0a] text-[#e8e4d9] overflow-hidden"
    >
      {/* subtle radial ink */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle at 30% 20%, rgba(218,41,28,0.10) 0%, transparent 50%), radial-gradient(circle at 75% 85%, rgba(255,255,255,0.06) 0%, transparent 45%)",
        }}
      />

      {/* Three floating samurai coins */}
      {coins.map((c, i) => (
        <img
          key={i}
          src="/assets/samurai-coin.png"
          alt=""
          aria-hidden
          className="absolute -translate-x-1/2 -translate-y-1/2"
          style={{
            top: c.top,
            left: c.left,
            width: c.size,
            height: c.size,
            transform: `translate(-50%,-50%) rotate(${c.rot}deg)`,
            animation: reduced ? "none" : `heroCoinFloat 4.5s ease-in-out ${c.delay} infinite`,
            filter: "drop-shadow(6px 6px 0 rgba(0,0,0,0.85))",
          }}
        />
      ))}

      <div className="relative h-full flex flex-col items-center justify-center px-6" style={{ zIndex: 5 }}>
        <div className="chip chip-red mb-6">SAMURAI · POINTS · GLORY</div>

        {/* Title with ivory background block behind red diagonal band to prevent color merge */}
        <div className="relative">
          {/* Diagonal band BEHIND the text */}
          <div
            aria-hidden
            className="absolute inset-x-[-30vw] top-1/2 -translate-y-1/2 h-16 sm:h-24 bg-[#da291c] border-y-4 border-black"
            style={{ transform: "translateY(-50%) rotate(-4deg)", zIndex: 0 }}
          />
          <h1
            className="relative font-anton uppercase text-6xl sm:text-8xl md:text-9xl leading-none tracking-tight text-center px-4"
            style={{
              zIndex: 2,
              color: "#efe9dc",
              WebkitTextStroke: "3px #0a0a0a",
              textShadow: "6px 6px 0 rgba(0,0,0,0.9)",
            }}
          >
            Greek<span style={{ color: "#0a0a0a", WebkitTextStroke: "3px #efe9dc" }}>GodBerry</span>
          </h1>
        </div>

        <p className="font-mono text-sm sm:text-base mt-8 opacity-90 max-w-md text-center">
          Sharpen the blade. The arena is loading.
        </p>

        <div className="mt-10 w-full max-w-md">
          <div
            data-testid={SPLASH.progress}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="brutal-border h-8 bg-[#efe9dc] relative"
          >
            <div
              className="absolute inset-y-0 left-0 bg-[#da291c]"
              style={{ width: `${pct}%`, transition: reduced ? "none" : "width 240ms linear" }}
            />
            <div className="absolute inset-0 flex items-center justify-between px-3 text-xs font-mono text-black mix-blend-difference">
              <span style={{ color: "#efe9dc" }}>LOADING</span>
              <span style={{ color: "#efe9dc" }}>{pct.toString().padStart(3, "0")}%</span>
            </div>
          </div>
        </div>

        <div className="mt-8 flex gap-4">
          {ready ? (
            <button
              data-testid={SPLASH.enter}
              onClick={enter}
              className="font-anton uppercase text-xl px-8 py-3 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow-ivory brutal-hover"
            >
              Enter the Arena →
            </button>
          ) : (
            showSkip && (
              <button
                data-testid={SPLASH.skip}
                onClick={enter}
                className="font-mono text-xs uppercase px-4 py-2 border-2 border-[#e8e4d9] text-[#e8e4d9] hover:bg-[#e8e4d9] hover:text-black transition-colors"
              >
                Skip intro
              </button>
            )
          )}
        </div>

        <div className="absolute bottom-6 font-mono text-[10px] uppercase tracking-widest opacity-70">
          18+ · Play Responsibly · GreekGodBerry Community
        </div>
      </div>
    </div>
  );
}
