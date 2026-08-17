import { useState, useEffect } from "react";
import { NAV } from "@/constants/testIds";

export default function AgeBanner() {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    try {
      setHidden(localStorage.getItem("ggb_age_dismiss") === "1");
    } catch { /* localStorage unavailable */ }
  }, []);
  if (hidden) return null;
  return (
    <div
      data-testid={NAV.ageBanner}
      className="fixed bottom-0 inset-x-0 z-50 bg-[#da291c] text-[#e8e4d9] border-t-4 border-black"
    >
      <div className="code-sequence max-w-[1400px] mx-auto px-4 py-2 flex items-center gap-3 text-xs sm:text-sm">
        <span className="font-anton uppercase text-lg tracking-tight shrink-0">18+</span>
        <p className="font-inter leading-snug">
          This site contains references to real-money gambling activity via linked platforms.
          Play responsibly. If gambling stops being fun, get help &mdash; call{" "}
          <a className="underline font-semibold" href="tel:18004264653" target="_blank" rel="noreferrer">1-800-GAMBLER</a>.
          Sponsorships & affiliate links disclosed on{" "}
          <a className="underline font-semibold" href="/legal">/legal</a>.
        </p>
        <button
          data-testid={NAV.ageBannerDismiss}
          onClick={() => { try { localStorage.setItem("ggb_age_dismiss", "1"); } catch { /* noop */ } setHidden(true); }}
          className="ml-auto shrink-0 font-mono uppercase text-xs px-3 py-1 border-2 border-black bg-black text-[#e8e4d9] hover:bg-[#e8e4d9] hover:text-black transition-colors"
          aria-label="Dismiss age warning"
        >
          I&apos;m 18+ · Dismiss
        </button>
      </div>
    </div>
  );
}
