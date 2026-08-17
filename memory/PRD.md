# GreekGodBerry Community Platform — PRD

## Original problem statement (verbatim intent)
Build a web-based community hub for the streamer "GreekGodBerry" with a Samurai-Brutalist art direction. Core pillars:
- Interactive splash with 0–100 real asset loading, desktop paw cursor, layered typography hero.
- Discord OAuth (owner email configured privately in the backend). Kick/Twitch linking via simulated chat challenge codes (deferred for MVP).
- Lockly leaderboard (server-side proxy + cache, UTC boundaries).
- Points ledger (append-only, atomic, idempotent).
- Store redemption (redeemable rewards).
- Stream Games (predictions/quizzes/raffles).
- Admin console for owner (create games, resolve, grant points, view users).
- Strict accessibility, reduced-motion fallbacks, mobile down to a $200 phone.
- 18+ gating and responsible-gambling disclosures.

## Product decisions (as of MVP)
- **Design**: Anton (headings), IBM Plex Mono (data), Inter (legal). Ink #0a0a0a, Washi Ivory #e8e4d9, Cinnabar #da291c. Zero rounding, solid block shadows.
- **Splash video / ghost video**: muted autoplay loop.
- **18+ gate**: persistent bottom banner (dismissible, localStorage).
- **Auth**: Discord OAuth only (Kick/Twitch verification deferred).
- **Names on leaderboard**: unmasked by default (per Lockly response); `mask=true` query flag available.

## Architecture
- **Frontend**: React 19 + React Router 7 + Tailwind + Motion. Splash → routed shell.
- **Backend**: FastAPI + Motor (MongoDB). All routes prefixed `/api`.
- **Auth**: HTTP-only cookie JWT (14d TTL) issued after Discord OAuth callback. Owner elevation on email match.
- **Cache**: In-memory 60s TTL on Lockly leaderboard responses (per `type`).
- **Points ledger**: `ledger` collection is append-only; unique sparse index on `idempotency_key`.

## Data model (MongoDB collections)
- `users` — discord_id (unique), username, email, avatar_url, role (viewer|owner), points_balance.
- `ledger` — user_id, delta, balance_after, reason, idempotency_key (unique sparse), ref, created_at.
- `rewards` — title, description, cost, stock (-1 = unlimited), image_url, active.
- `games` — title, kind (prediction|quiz|raffle), status, entry_cost, reward_pool, prompt, options, winning_option.
- `game_entries` — game_id, user_id, choice, stake, created_at.

## API endpoints (implemented)
- `GET  /api/` — health.
- `GET  /api/auth/discord/login` → { url } (redirect to Discord authorize).
- `GET  /api/auth/discord/callback?code=...` → sets cookie, redirects to `/?auth=success`.
- `GET  /api/auth/me` — current user (401 if unauth).
- `POST /api/auth/logout` — clears cookie.
- `GET  /api/leaderboard?type=daily|weekly|monthly&mask=true|false` — Lockly proxy, 60s cache.
- `GET  /api/points/me` — balance.
- `GET  /api/points/ledger?limit=50` — user ledger.
- `GET  /api/store/rewards` — active rewards.
- `POST /api/store/redeem { reward_id, idempotency_key? }` — atomic redeem.
- `GET  /api/games` — list games.
- `POST /api/games/join { game_id, choice? }` — user entry (one per game).
- Admin (owner-only):
  - `POST /api/admin/games` — create game.
  - `POST /api/admin/games/{id}/resolve { winning_option? }` — payout winners from pool.
  - `POST /api/admin/rewards` — add reward.
  - `POST /api/admin/points/grant { discord_id, delta, reason }`.
  - `GET  /api/admin/users` — all users.

## What's implemented (Feb 2026)
- ✅ Samurai-brutalist design tokens (fonts, colors, brutal borders/shadows, paw cursor).
- ✅ Splash screen with 0–100 real asset loading, skip/enter, localStorage skip on repeat.
- ✅ Layered hero (background type, cutout, red diagonal band, coin greenscreen video, social chips).
- ✅ Persistent 18+ bottom banner with responsible-gambling disclosure.
- ✅ Discord OAuth flow with cookie session, owner auto-elevation.
- ✅ Lockly leaderboard proxy w/ 60s cache; daily/weekly/monthly tabs; podium + dense table; ghost video overlay.
- ✅ Store with reward grid, confirm modal, redeem endpoint (idempotent, atomic ledger update).
- ✅ Stream Games list + join flow with option selection.
- ✅ Admin console (create games, grant points, users table).
- ✅ 4 seed rewards on first boot.

# CHANGELOG

## 2026-02-17 — Home redesign v2 (Dribbble Japanese-history vibe)
- Centered GreekGodBerry cutout with Enso-style black ring + red disc behind him.
- Background: 8 floating/drifting social platform tiles (Twitch, Kick, YouTube, Discord, Instagram, X) with subtle 9s drift animation.
- Added Instagram to the socials + updated URLs (Discord invite quEGjqWrT, X → greekgodberryx).
- Katakana display type in soft opacity behind hero + Japanese meta labels on the black stat rail (スシ, コード, ライブ, 気分).
- Left column: mythology-style block copy ("SAMURAI OF THE SLOTS…").
- Right column: bordered ORIGIN / CODE / PATH meta strip.
- Added **FeatureCards** section ("The Codex · Three Paths") with M1/M2/M3 brutal cards, kanji tags (目 / 頭 / 戦), red circular status dots, "RESTORATION IN PROGRESS" chips.
- Videos: FFmpeg chroma-keyed both mp4s to VP9 webm with alpha — no runtime keying needed. Ghost + coin now transparent-background.
- Cursor: replaced red-paw SVG with a pixel-art yellow paw (matches user reference), base64 data-URI (works across webpack builds).
- Removed unused ChromaVideo.jsx and the old mp4 files.

## 2026-02-17 — MVP v1
- Discord OAuth cookie session (owner auto-elevated by email match).
- Lockly leaderboard proxy w/ 60s cache, daily/weekly/monthly tabs, podium + dense table.
- Store with 4 seeded rewards + confirm-modal redemption + append-only ledger + idempotency.
- Stream Games list + join flow, admin can create/resolve games and grant points.
- Samurai brutalist splash screen with real-asset 0-100 loader.
- 18+ persistent bottom banner.
- Backend testing: 28/28 pytest cases passing.

## Backlog / not yet built
- **P1**: Game resolve UI in Admin (endpoint exists — no UI button yet).
- **P1**: Points ledger user-facing page (`/me` transactions).
- **P2**: Simulated Kick/Twitch verification codes (deferred by user).
- **P2**: Legal page `/legal` (Privacy, Terms, Giveaway Rules).
- **P2**: Public profile pages per user.
- **P2**: Object storage integration for owner-uploaded reward images.
- **P3**: E2E test suite with Playwright.
- **P3**: Rate limits + brute force protection.
- **P3**: Deployment health checks.

## External integrations
- **Discord OAuth**: Client ID is configured in the backend (secret stays in backend/.env).
- **Lockly**: API key configured in backend/.env; server proxy only, never exposed to browser.
