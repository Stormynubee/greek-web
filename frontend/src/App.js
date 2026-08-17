import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
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

function Shell() {
  usePawCursor();
  const [showSplash, setShowSplash] = useState(true);

  useEffect(() => {
    try {
      if (localStorage.getItem("ggb_splash_seen") === "1") setShowSplash(false);
    } catch { /* localStorage unavailable */ }
  }, []);

  if (showSplash) return <Splash onDone={() => setShowSplash(false)} />;

  return (
    <BrowserRouter>
      <Navbar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/leaderboards" element={<LeaderboardsPage />} />
        <Route path="/store" element={<StorePage />} />
        <Route path="/stream-games" element={<StreamGamesPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
      <AgeBanner />
    </BrowserRouter>
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
