import { useEffect } from "react";

/** Apply paw cursor class to <html> only when the primary pointer is fine (mouse). */
export default function usePawCursor() {
  useEffect(() => {
    const mq = window.matchMedia("(pointer: fine)");
    const rm = window.matchMedia("(prefers-reduced-motion: reduce)");
    document.documentElement.style.setProperty(
      "--cursor-cat-closed",
      'url("/assets/cat-cursor-closed-small.png")'
    );
    document.documentElement.style.setProperty(
      "--cursor-cat-open",
      'url("/assets/cat-cursor-open-small.png")'
    );
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
    const press = () => {
      if (mq.matches && !rm.matches) document.documentElement.classList.add("paw-clicking");
    };
    const release = () => document.documentElement.classList.remove("paw-clicking");
    window.addEventListener("pointerdown", press, true);
    window.addEventListener("pointerup", release, true);
    window.addEventListener("pointercancel", release, true);
    window.addEventListener("blur", release);
    return () => {
      mq.removeEventListener?.("change", apply);
      rm.removeEventListener?.("change", apply);
      window.removeEventListener("pointerdown", press, true);
      window.removeEventListener("pointerup", release, true);
      window.removeEventListener("pointercancel", release, true);
      window.removeEventListener("blur", release);
      document.documentElement.classList.remove("paw-clicking");
      document.documentElement.style.removeProperty("--cursor-cat-closed");
      document.documentElement.style.removeProperty("--cursor-cat-open");
    };
  }, []);
}
