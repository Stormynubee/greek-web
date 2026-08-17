import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { NAV } from "@/constants/testIds";

const linkBase =
  "font-anton uppercase text-lg px-3 py-1 border-2 border-transparent hover:border-[#da291c] hover:text-[#da291c] transition-colors";
const linkActive = "text-[#da291c] border-[#da291c]";

export default function Navbar() {
  const { user, loginDiscord, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header
      data-testid={NAV.root}
      className="sticky top-0 z-40 bg-[#0a0a0a] border-b-4 border-[#da291c] nav-enter"
    >
      <div className="max-w-[1400px] mx-auto px-4 sm:px-6 py-3 flex items-center gap-2 sm:gap-4">
        <Link
          data-testid={NAV.logo}
          to="/"
          className="font-anton uppercase text-2xl sm:text-3xl tracking-tight text-[#e8e4d9] hover:text-[#da291c] nav-brand"
        >
          Greek<span className="text-[#da291c]">GodBerry</span>
        </Link>

        <nav className="hidden md:flex items-center gap-1 ml-6 flex-1">
          <NavLink data-testid={NAV.linkHome} to="/" end
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Home</NavLink>
          <NavLink data-testid={NAV.linkLeaderboard} to="/leaderboards"
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Leaderboards</NavLink>
          <NavLink data-testid={NAV.linkStore} to="/store"
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Point Shop</NavLink>
          <NavLink data-testid={NAV.linkGames} to="/stream-games"
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Games</NavLink>
          <NavLink to="/giveaways"
            className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Giveaways</NavLink>
          {user?.role === "owner" && (
            <NavLink data-testid={NAV.linkAdmin} to="/admin"
              className={({ isActive }) => `${linkBase} ${isActive ? linkActive : ""}`}>Admin</NavLink>
          )}
        </nav>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          {user ? (
            <>
              <div data-testid={NAV.points} className="chip chip-red hidden sm:inline-flex" title="Points balance">
                <img src="/assets/samurai-coin.png" alt="" className="w-4 h-4" />
                {user.points_balance} pts
              </div>
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.username}
                  className="w-9 h-9 border-2 border-[#e8e4d9] object-cover" />
              ) : (
                <div className="w-9 h-9 border-2 border-[#e8e4d9] bg-[#da291c] font-anton text-xl flex items-center justify-center">
                  {user.username?.[0]?.toUpperCase() || "?"}
                </div>
              )}
              <span className="font-mono text-xs uppercase hidden md:inline">{user.username}</span>
              <button
                data-testid={NAV.logout}
                onClick={() => { logout(); navigate("/"); }}
                className="font-mono text-xs uppercase px-3 py-2 border-2 border-[#e8e4d9] button-feedback"
              >
                Logout
              </button>
            </>
          ) : (
            <button
              data-testid={NAV.loginDiscord}
              onClick={loginDiscord}
              className="font-anton uppercase text-base px-4 py-2 bg-[#da291c] text-[#e8e4d9] brutal-border brutal-shadow-ivory brutal-hover button-feedback"
            >
              Login with Discord
            </button>
          )}
        </div>
      </div>

      {/* Mobile subnav */}
      <div className="md:hidden bg-black border-t-2 border-[#da291c] overflow-x-auto flex items-center gap-1 px-2 py-1">
        <NavLink to="/" end className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Home</NavLink>
        <NavLink to="/leaderboards" className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Boards</NavLink>
        <NavLink to="/store" className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Shop</NavLink>
        <NavLink to="/stream-games" className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Games</NavLink>
        <NavLink to="/giveaways" className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Gift</NavLink>
        {user?.role === "owner" && (
          <NavLink to="/admin" className={({ isActive }) => `${linkBase} shrink-0 ${isActive ? linkActive : ""}`}>Admin</NavLink>
        )}
      </div>
    </header>
  );
}
