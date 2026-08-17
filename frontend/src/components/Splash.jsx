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
  { url: "/assets/splash.webp", kind: "image" },
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
      // video: fetch as blob to count progress without playing
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
    // Repeat visitor skip
    try {
      if (localStorage.getItem("ggb_splash_seen") === "1") {
        onDone?.();
        return;
      }
    } catch { /* localStorage unavailable */ }

    let cancelled = false;
    const start = performance.now();
    let done = 0;

    // failsafe: after 8s force complete
    const failsafe = setTimeout(() => {
      if (!cancelled) { setPct(100); setReady(true); }
    }, 8000);

    // show skip after 2s
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
      // Min visible time 900ms for polish (unless reduced motion)
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

  return (
    <div
      data-testid={SPLASH.root}
      className="fixed inset-0 z-[100] bg-[#0a0a0a] text-[#e8e4d9] overflow-hidden"
    >
      {/* washi splash bg with red overlay */}
      <div
        className="absolute inset-0 opacity-40"
        style={{
          backgroundImage: "url(/assets/splash.webp)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          filter: "grayscale(1) contrast(1.1)",
        }}
      />
      <div className="absolute inset-0 bg-[#0a0a0a]/70" />

      {/* Diagonal ink slash */}
      <div
        aria-hidden
        className="absolute -left-20 top-1/3 w-[140%] h-24 bg-[#da291c] slash-anim"
        style={{ boxShadow: "0 8px 0 0 #000" }}
      />

      <div className="relative h-full flex flex-col items-center justify-center px-6">
        <div className="chip chip-red mb-6">SAMURAI · POINTS · GLORY</div>
        <h1 className="font-anton uppercase text-6xl sm:text-8xl md:text-9xl leading-none tracking-tight text-center">
          Greek<span className="text-[#da291c]">GodBerry</span>
        </h1>
        <p className="font-mono text-sm sm:text-base mt-4 opacity-80 max-w-md text-center">
          Sharpen the blade. The arena is loading.
        </p>

        {/* Progress bar */}
        <div className="mt-10 w-full max-w-md">
          <div
            data-testid={SPLASH.progress}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            className="brutal-border h-8 bg-black relative"
          >
            <div
              className="absolute inset-y-0 left-0 bg-[#da291c]"
              style={{ width: `${pct}%`, transition: reduced ? "none" : "width 240ms linear" }}
            />
            <div className="absolute inset-0 flex items-center justify-between px-3 text-xs font-mono">
              <span>LOADING</span>
              <span>{pct.toString().padStart(3, "0")}%</span>
            </div>
          </div>
        </div>

        {/* CTAs */}
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

        <div className="absolute bottom-6 font-mono text-[10px] uppercase tracking-widest opacity-60">
          18+ · Play Responsibly · GreekGodBerry Community
        </div>
      </div>
    </div>
  );
}
