import { useCallback, useState } from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import "@/App.css";
import { AuthProvider } from "@/contexts/AuthContext";
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
      <RouteStage />
      <AgeBanner />
    </BrowserRouter>
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
