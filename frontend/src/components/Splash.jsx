import { useEffect, useState, useRef } from "react";
import { SPLASH } from "@/constants/testIds";
import { SPLASH_STORAGE_KEY } from "@/constants/splash";

const ASSETS = [
  { url: "/assets/greek-cutout.webp", kind: "image" },
  { url: "/assets/samurai-coin.png", kind: "image" },
  { url: "/assets/samurai-walking.webp", kind: "image" },
  { url: "/assets/paw-cursor.png", kind: "image" },
  { url: "/assets/samurai-coin-greenscreen.mp4", kind: "video" },
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

// deterministic falling coin lanes
const RAIN = Array.from({ length: 14 }).map((_, i) => ({
  left: `${(i * 7.3 + 3) % 96}%`,
  size: 24 + ((i * 17) % 40),
  duration: 4 + ((i * 11) % 9),
  delay: (i * 0.37) % 5,
  rot: (i % 2 ? 1 : -1) * ((i * 13) % 25),
}));

export default function Splash({ onDone }) {
  const [pct, setPct] = useState(0);
  const [ready, setReady] = useState(false);
  const doneRef = useRef(false);
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  useEffect(() => {
    let cancelled = false;
    const start = performance.now();
    let done = 0;
    const failsafe = setTimeout(() => {
      if (!cancelled) { setPct(100); setReady(true); }
    }, 8000);

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
    };
  }, [reduced]);

  const enter = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    try { localStorage.setItem(SPLASH_STORAGE_KEY, "1"); } catch { /* noop */ }
    onDone?.();
  };

  return (
    <div
      data-testid={SPLASH.root}
      className="fixed inset-0 z-[100] bg-[#0a0a0a] text-[#e8e4d9] overflow-hidden"
    >
      {/* radial ink */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          backgroundImage:
            "radial-gradient(circle at 30% 20%, rgba(218,41,28,0.10) 0%, transparent 50%), radial-gradient(circle at 75% 85%, rgba(255,255,255,0.06) 0%, transparent 45%)",
        }}
      />

      {/* Coin rain */}
      {!reduced && RAIN.map((c, i) => (
        <img
          key={i}
          src="/assets/samurai-coin.png"
          alt=""
          aria-hidden
          className="absolute top-0"
          style={{
            left: c.left,
            width: c.size,
            height: c.size,
            animation: `coinRain ${c.duration}s linear ${c.delay}s infinite`,
            transform: `rotate(${c.rot}deg)`,
            filter: "drop-shadow(3px 3px 0 rgba(0,0,0,0.6))",
            opacity: 0.9,
          }}
        />
      ))}

      {/* Animated samurai centerpiece: sword-draw sequence */}
      {!reduced && (
        <img
          src="/assets/samurai-walking.webp"
          alt=""
          aria-hidden
          className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-40 pointer-events-none select-none"
          style={{
            width: "min(70vw, 620px)",
            maxHeight: "80vh",
            zIndex: 1,
            filter: "grayscale(0.4) contrast(1.05) drop-shadow(0 0 30px rgba(218,41,28,0.35))",
          }}
        />
      )}

      <div className="relative h-full flex flex-col items-center justify-center px-6" style={{ zIndex: 5 }}>
        <div className="chip chip-red mb-6">SAMURAI · POINTS · GLORY</div>

        <div className="relative">
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
            <div className="absolute inset-0 flex items-center justify-between px-3 text-xs font-mono">
              <span style={{ color: "#efe9dc", textShadow: "1px 1px 0 #000" }}>LOADING</span>
              <span style={{ color: "#efe9dc", textShadow: "1px 1px 0 #000" }}>{pct.toString().padStart(3, "0")}%</span>
            </div>
          </div>
        </div>

        <div className="mt-8 flex gap-4 min-h-12 items-center">
          {ready && (
            <button
              data-testid={SPLASH.enter}
              onClick={enter}
              className="font-anton uppercase text-xl px-8 py-3 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow-ivory brutal-hover button-feedback"
            >
              Enter the Arena →
            </button>
          )}
        </div>

        <div className="absolute bottom-6 font-mono text-[10px] uppercase tracking-widest opacity-70">
          18+ · Play Responsibly · GreekGodBerry Community
        </div>
      </div>
    </div>
  );
}
