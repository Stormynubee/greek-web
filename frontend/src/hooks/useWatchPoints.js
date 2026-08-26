import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

/** 1 pt per 240s = 15 pts/hr while the stream is live and the tab is visible.
 *  Fire-and-forget: a failed beat is harmless and the server buckets by time. */
const BEAT_MS = 240_000;

export function useWatchPoints({ enabled, isLive }) {
  const timerRef = useRef(null);
  const wasVisible = useRef(false);

  useEffect(() => {
    if (!enabled || !isLive) return undefined;

    const sendBeat = () => {
      // Re-check visibility so a parked/hidden tab never earns.
      if (document.visibilityState !== "visible") return;
      api
        .post("/internal/points/watch-beat", {}, { timeout: 8000 })
        .catch(() => {
          /* at-most-once; server dedups by time bucket */
        });
    };

    const loop = () => {
      sendBeat();
      timerRef.current = setTimeout(loop, BEAT_MS);
    };

    const onVisibility = () => {
      const visible = document.visibilityState === "visible";
      if (visible && !wasVisible.current) {
        // Returning to the tab mid-cycle: send a beat now (server dedups).
        sendBeat();
      }
      wasVisible.current = visible;
    };

    wasVisible.current = document.visibilityState === "visible";
    loop();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled, isLive]);
}