import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import usePawCursor from "@/hooks/usePawCursor";
import Splash from "@/components/Splash";
import Navbar from "@/components/Navbar";
import AgeBanner from "@/components/AgeBanner";
import HomePage from "@/pages/HomePage";
import { SPLASH_STORAGE_KEY } from "@/constants/splash";

const LeaderboardsPage = lazy(() => import("@/pages/LeaderboardsPage"));
const StorePage = lazy(() => import("@/pages/StorePage"));
const StreamGamesPage = lazy(() => import("@/pages/StreamGamesPage"));
const AdminPage = lazy(() => import("@/pages/AdminPage"));
const AdminLoginPage = lazy(() => import("@/pages/AdminLoginPage"));
const GiveawaysPage = lazy(() => import("@/pages/GiveawaysPage"));
const LegalPage = lazy(() => import("@/pages/LegalPage"));

function Shell() {
  usePawCursor();
  const { bootstrapError, authError, clearAuthError } = useAuth();
  const [showSplash, setShowSplash] = useState(() => {
    try {
      return localStorage.getItem(SPLASH_STORAGE_KEY) !== "1";
    } catch {
      return true;
    }
  });
  const finishSplash = useCallback(() => setShowSplash(false), []);

  if (showSplash) return <Splash onDone={finishSplash} />;

  return (
    <BrowserRouter>
      <Navbar />
      <AuthFeedback />
      {(bootstrapError || authError) && (
        <div
          role="alert"
          className="api-bootstrap-alert fixed top-20 right-4 z-50 max-w-sm brutal-border brutal-shadow bg-[#da291c] text-[#efe9dc] p-3 font-mono text-xs"
        >
          <div>{authError || bootstrapError}</div>
          {authError && (
            <button
              type="button"
              onClick={clearAuthError}
              className="mt-2 border border-[#efe9dc] px-2 py-1 uppercase"
            >
              Dismiss
            </button>
          )}
        </div>
      )}
      <RouteStage />
      <AgeBanner />
    </BrowserRouter>
  );
}

function AuthFeedback() {
  const location = useLocation();
  const navigate = useNavigate();
  const [message, setMessage] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const authResult = params.get("auth");
    if (!authResult) return undefined;
    const reason = params.get("reason");
    const failureMessages = {
      oauth_denied: "Discord login was cancelled in Discord.",
      state_invalid: "Discord login expired or was opened in another tab. Please try again.",
      token_exchange: "Discord authorization could not be exchanged. Check the configured redirect URI.",
      discord_profile: "Discord authorized the login, but did not return your profile.",
      oauth_failed: "Discord login could not be completed. Please try again.",
    };
    setMessage(
      authResult === "success"
        ? "Discord connected. Welcome to the arena."
        : failureMessages[reason] || "Discord login could not be completed. Please try again."
    );
    params.delete("auth");
    params.delete("reason");
    params.delete("auth_ticket");
    navigate(
      {
        pathname: location.pathname,
        search: params.toString() ? `?${params.toString()}` : "",
      },
      { replace: true }
    );
  }, [location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!message) return undefined;
    const timer = window.setTimeout(() => setMessage(null), 5000);
    return () => window.clearTimeout(timer);
  }, [message]);

  if (!message) return null;
  return (
    <div
      role="status"
      className="fixed top-20 left-1/2 -translate-x-1/2 z-50 brutal-border brutal-shadow bg-[#efe9dc] text-black px-4 py-3 font-mono text-xs"
    >
      {message}
    </div>
  );
}

function RouteStage() {
  const location = useLocation();

  return (
    <div key={location.pathname} className="route-enter">
      <Suspense fallback={<RouteLoading />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/leaderboards" element={<LeaderboardsPage />} />
          <Route path="/store" element={<StorePage />} />
          <Route path="/stream-games" element={<StreamGamesPage />} />
          <Route path="/giveaways" element={<GiveawaysPage />} />
          <Route path="/admin/login" element={<AdminLoginPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/legal" element={<LegalPage />} />
          <Route path="*" element={<HomePage />} />
        </Routes>
      </Suspense>
    </div>
  );
}

function RouteLoading() {
  return (
    <div
      className="min-h-[50vh] flex items-center justify-center bg-[#0a0a0a] text-[#efe9dc] px-4"
      role="status"
      aria-live="polite"
    >
      <div className="font-mono text-xs uppercase tracking-widest">Loading arena…</div>
    </div>
  );
}

export default function App() {
  return (
    <div className="App">
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </div>
  );
}
