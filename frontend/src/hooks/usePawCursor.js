import { useEffect } from "react";

/** Apply paw cursor class to <html> only when the primary pointer is fine (mouse). */
export default function usePawCursor() {
  useEffect(() => {
    const mq = window.matchMedia("(pointer: fine)");
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => {
      if (mq.matches && !rm.matches) {
        document.documentElement.classList.add("paw-cursor");
      } else {
        document.documentElement.classList.remove("paw-cursor");
      }
    };
    apply();
    mq.addEventListener?.("change", apply);
    rm.addEventListener?.("change", apply);
    return () => {
      mq.removeEventListener?.("change", apply);
      rm.removeEventListener?.("change", apply);
    };
  }, []);
}
