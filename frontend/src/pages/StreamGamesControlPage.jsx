import { Link } from "react-router-dom";
import StreamGamesControl from "@/components/StreamGamesControl";

/**
 * Standalone page for the Stream Games control console.
 *
 * Lives at /admin/stream-games and intentionally does NOT depend on the main
 * site's admin auth state, so logging out of the main dashboard (/admin) does
 * not tear down (or lock) this console. Its login is a separate Discord OAuth
 * session against the greek-bingo backend, managed entirely by
 * StreamGamesControl itself.
 */
export default function StreamGamesControlPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-[#efe9dc] px-4 sm:px-6 py-8">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-center justify-between gap-3 mb-6">
          <div>
            <div className="chip chip-red mb-2">STREAMER CONSOLE</div>
            <h1 className="font-anton uppercase text-4xl sm:text-5xl leading-none tracking-tight">
              Stream Games
            </h1>
            <p className="font-mono text-xs mt-2 opacity-70">
              Run Kick/Twitch stream games from here. Uses its own Discord login —
              independent of the main admin dashboard.
            </p>
          </div>
          <Link
            to="/admin"
            className="font-mono text-xs uppercase px-3 py-2 border-2 border-[#efe9dc] shrink-0"
          >
            ← Admin
          </Link>
        </div>

        <StreamGamesControl />
      </div>
    </div>
  );
}