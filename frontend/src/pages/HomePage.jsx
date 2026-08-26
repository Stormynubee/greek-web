import { useEffect, useState } from "react";
import Hero from "@/components/Hero";
import FeatureCards from "@/components/FeatureCards";
import CatCrewReference from "@/components/CatCrewReference";
import KickLiveStage from "@/components/KickLiveStage";
import { useAuth } from "@/contexts/AuthContext";
import { useWatchPoints } from "@/hooks/useWatchPoints";
import { API_CONFIG_ERROR, api } from "@/lib/api";

export default function HomePage() {
  const { user } = useAuth();
  const [liveStatus, setLiveStatus] = useState({ is_live: false, loading: true });

  // 15 pts/hr while a logged-in viewer watches the live stream (tab visible).
  useWatchPoints({ enabled: Boolean(user), isLive: liveStatus.is_live === true });

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    if (API_CONFIG_ERROR) {
      setLiveStatus({ is_live: false, loading: false, unavailable: true });
      return () => {
        active = false;
        controller.abort();
      };
    }

    api.get("/live", { signal: controller.signal })
      .then((response) => {
        if (active) setLiveStatus({ ...response.data, loading: false });
      })
      .catch((error) => {
        if (active && error?.code !== "ERR_CANCELED") {
          setLiveStatus({ is_live: false, loading: false, unavailable: true });
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return (
    <>
      <Hero liveStatus={liveStatus} />
      <FeatureCards />
      <CatCrewReference />
      <KickLiveStage liveStatus={liveStatus} />

      {/* Legal / disclosure strip */}
      <footer className="bg-black border-t-4 border-[#da291c] py-8 px-4 sm:px-6 mb-14">
        <div className="code-sequence max-w-[1400px] mx-auto font-inter text-xs opacity-80 space-y-2 text-[#efe9dc]">
          <p><strong className="font-anton uppercase text-[#da291c] tracking-wide">Disclosure:</strong> Links marked with ↗ may be affiliated. Using code GREEK33 supports the channel at no cost to you.</p>
          <p><strong className="font-anton uppercase text-[#da291c] tracking-wide">Responsible Gambling:</strong> Gambling should be entertainment, not income. Never wager money you cannot afford to lose. Free confidential help at 1-800-GAMBLER (US) / BeGambleAware.org (UK).</p>
          <p className="opacity-60">© {new Date().getFullYear()} GreekGodBerry Community · A samurai brutalist experience.</p>
        </div>
      </footer>
    </>
  );
}
