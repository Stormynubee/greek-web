import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from "react-router-dom";
import "@/App.css";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import usePawCursor from "@/hooks/usePawCursor";
import Splash from "@/components/Splash";
import Navbar from "@/components/Navbar";
import AgeBanner from "@/components/AgeBanner";
import HomePage from "@/pages/HomePage";
import LeaderboardsPage from "@/pages/LeaderboardsPage";
import StorePage from "@/pages/StorePage";
import StreamGamesPage from "@/pages/StreamGamesPage";
import AdminPage from "@/pages/AdminPage";
import AdminLoginPage from "@/pages/AdminLoginPage";
import GiveawaysPage from "@/pages/GiveawaysPage";
import LegalPage from "@/pages/LegalPage";
import { SPLASH_STORAGE_KEY } from "@/constants/splash";

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
          className="fixed top-20 right-4 z-50 max-w-sm brutal-border brutal-shadow bg-[#da291c] text-[#efe9dc] p-3 font-mono text-xs"
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
    setMessage(
      authResult === "success"
        ? "Discord connected. Welcome to the arena."
        : "Discord login was cancelled or could not be completed."
    );
    params.delete("auth");
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
