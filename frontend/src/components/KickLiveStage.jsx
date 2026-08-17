import { useState } from "react";
import { HOME } from "@/constants/testIds";

const KICK_CHANNEL = "greekgodberry";
const KICK_URL = `https://kick.com/${KICK_CHANNEL}`;
const KICK_PLAYER_URL = `https://player.kick.com/${KICK_CHANNEL}?autoplay=true&muted=true&playsinline=true`;

export default function KickLiveStage({ liveStatus = {} }) {
  const [playerActive, setPlayerActive] = useState(false);
  const isLive = liveStatus.is_live === true;
  const isChecking = liveStatus.loading === true;

  return (
    <section
      data-testid={HOME.kickStage}
      className="bg-[#111] text-[#efe9dc] border-t-4 border-[#da291c] py-14 px-4 sm:px-6"
    >
      <div className="max-w-[1400px] mx-auto">
        <div className="flex flex-wrap items-end justify-between gap-5 mb-7">
          <div>
            <div className="chip chip-red mb-3">KICK · LIVE DECK</div>
            <h2 className="font-anton uppercase text-5xl sm:text-7xl leading-[0.86] tracking-tight">
              Watch the <span className="text-[#da291c]">Arena</span>
            </h2>
            <p className="font-mono text-xs sm:text-sm uppercase opacity-65 mt-4 max-w-xl">
              Live playback from GreekGodBerry&apos;s Kick channel, placed where
              the action starts.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div
              data-testid={HOME.kickLiveAlert}
              role="status"
              aria-live="polite"
              className="inline-flex items-center gap-2 border-2 border-[#efe9dc] px-3 py-2 font-mono text-[10px] uppercase"
            >
              <span className={`w-2 h-2 rounded-full ${isLive ? "bg-[#da291c] animate-pulse" : "bg-[#7a7a7a]"}`} />
              {isChecking
                ? "Checking live signal"
                : isLive
                  ? "GreekGodBerry is live now"
                  : "Channel quiet · latest replay on Kick"}
            </div>
            <a
              href={KICK_URL}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-[10px] uppercase px-3 py-2 border-2 border-[#53fc18] text-[#53fc18] hover:bg-[#53fc18] hover:text-black transition-colors"
            >
              Open Kick ↗
            </a>
          </div>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)] gap-6 items-stretch">
          <div className="brutal-border-ivory bg-black p-2 sm:p-3 brutal-shadow-red">
            {playerActive ? (
              <div className="relative aspect-video overflow-hidden bg-black">
                <iframe
                  data-testid={HOME.kickPlayer}
                  title="GreekGodBerry live playback on Kick"
                  src={KICK_PLAYER_URL}
                  loading="lazy"
                  allow="autoplay; fullscreen; picture-in-picture"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                  className="absolute inset-0 h-full w-full border-0"
                />
                <div className="absolute top-3 left-3 pointer-events-none chip chip-red text-[10px]">
                  KICK PLAYER · LIVE FEED
                </div>
              </div>
            ) : (
              <button
                type="button"
                data-testid={HOME.kickActivate}
                onClick={() => setPlayerActive(true)}
                aria-label="Load GreekGodBerry's Kick playback"
                className="group relative block w-full aspect-video overflow-hidden text-left bg-[#171717] focus-visible:outline-none"
                style={{
                  backgroundImage:
                    "radial-gradient(circle at 50% 38%, rgba(218,41,28,0.52), transparent 45%), linear-gradient(135deg, #171717 0%, #070707 100%)",
                }}
              >
                <span
                  aria-hidden
                  className="absolute inset-0 opacity-20"
                  style={{
                    backgroundImage:
                      "linear-gradient(rgba(239,233,220,0.16) 1px, transparent 1px), linear-gradient(90deg, rgba(239,233,220,0.16) 1px, transparent 1px)",
                    backgroundSize: "36px 36px",
                  }}
                />
                <span className="absolute top-4 left-4 font-mono text-[10px] uppercase tracking-[0.2em] text-[#efe9dc]/70">
                  KICK / @{KICK_CHANNEL}
                </span>
                <span className="absolute top-4 right-4 chip text-[10px]">
                  {isLive ? "LIVE NOW" : "CHANNEL PREVIEW"}
                </span>
                <span className="absolute inset-0 flex flex-col items-center justify-center text-center px-5">
                  <span className="flex items-center justify-center w-20 h-20 sm:w-24 sm:h-24 border-4 border-[#efe9dc] bg-[#da291c] text-[#efe9dc] font-anton text-3xl transition-transform duration-200 group-hover:scale-110 group-focus-visible:scale-110">
                    ▶
                  </span>
                  <span className="font-anton uppercase text-2xl sm:text-4xl mt-5">
                    {isLive ? "Tap to watch live" : "Tap to load playback"}
                  </span>
                  <span className="font-mono text-[10px] uppercase opacity-65 mt-2">
                    The Kick player loads only when you choose to watch
                  </span>
                </span>
                <span className="absolute bottom-4 left-4 right-4 flex items-center justify-between font-mono text-[10px] uppercase opacity-60">
                  <span>16:9 · fullscreen ready</span>
                  <span>sound starts muted</span>
                </span>
              </button>
            )}
          </div>

          <aside className="brutal-border-ivory bg-[#efe9dc] text-black p-5 flex flex-col justify-between">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-60">Playback protocol</div>
              <ol className="mt-5 space-y-4 font-mono text-xs uppercase">
                <li className="flex gap-3">
                  <span className="font-anton text-2xl text-[#da291c] leading-none">01</span>
                  <span>Tap the preview to activate the live deck.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-anton text-2xl text-[#da291c] leading-none">02</span>
                  <span>Use the player controls to unmute or go fullscreen.</span>
                </li>
                <li className="flex gap-3">
                  <span className="font-anton text-2xl text-[#da291c] leading-none">03</span>
                  <span>When the stream is quiet, open Kick for the latest replay.</span>
                </li>
              </ol>
            </div>
            <div className="border-t-2 border-black mt-7 pt-4 font-mono text-[10px] uppercase">
              <div className="flex justify-between gap-3">
                <span className="opacity-60">Channel</span>
                <span>@{KICK_CHANNEL}</span>
              </div>
              <div className="flex justify-between gap-3 mt-2">
                <span className="opacity-60">Source</span>
                <span>Kick player</span>
              </div>
            </div>
          </aside>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 mt-5 font-mono text-[10px] uppercase opacity-60">
          <span>
            {playerActive
              ? "Playback is served directly by Kick."
              : "The third-party player stays unloaded until interaction."}
          </span>
          <a href={KICK_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-[#53fc18]">
            View latest on Kick →
          </a>
        </div>
      </div>
    </section>
  );
}
