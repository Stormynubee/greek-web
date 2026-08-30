# GreekGodBerry — Stream Games Guide
*For streamer + co-streamer operators · Run interactive Kick/Twitch chat games on stream*

**Full URLs (prefix):**
- Console (you control games): `https://www.greekgambles.com/admin/stream-games` → **Connect Discord**
- Overlays (viewer-facing, add to OBS): `https://greek-bingo-admin.vercel.app/overlay/...`

> **No need to be live.** The bots connect to Kick's chat feed directly — anyone typing chat commands registers even when the stream is offline.

---

## 1. Chat vs Streamer
Chat predicts whether **chat** or the **streamer** wins a challenge.

1. Console → **Chat vs Streamer** → **Create Match** (optional: **Set Challenge**)
2. **Open Round** → chat votes
3. Console → **Lock Round** → pick **Chat correct / Streamer correct** → **Resolve Round**
4. **End Match** when done

**Chat:** `!win chat` · `!win streamer` · `!score` · `!streak` · `!status` · `!leaderboard` · `!rules`
**Overlay:** `/overlay/chat-vs-streamer`

---

## 2. Bonus Bingo 🎯
Viewers **join**, get drawn to a **square**, pick a bonus buy. A profit turns it **green**. Complete a line to win.

1. Console → **Bonus Bingo** → **Create Game** → **Set Keyword** (e.g. `!join`) → **Open Registration**
2. Chat joins with `!join` / `!join <slot>`
3. **Start Game** → **Spin Cell** → **Draw Player**
4. Drawn player types `!slot <name>` (or you **Set Slot**)
5. **Mark Win** / **Mark Loss**
6. Repeat until a **line completes** → **Complete**

**Chat:** `!join` · `!join <slot>` · `!slot <name>`
**Overlay:** `/overlay/bonus-bingo` (grid, names, current draw, lines)

---

## 3. Climb the Ladder
One climber, 6 rungs, 250 → 2,000 points. Chat predicts each step.

1. Console → **Climb the Ladder** → **Create Run**
2. Use console **Pass / Fail / Cash Out / Climb** per rung

**Chat:** `!climb pass` · `!climb fail` · `!climb cashout` · `!climb higher` · `!climb status` · `!climb rules`
**Overlay:** `/overlay/climb-the-ladder`

---

## 4. Bonus Hunt
A collection of bonus slots; chat suggests slots and guesses values.

1. Console → **Bonus Hunt** → **Create Hunt** → **Start Hunt**
2. **Open Guessing** → chat guesses
3. **Complete** when done

**Chat:** `!sr <slot>` · `!guess <amount>`
**View:** hunt-tracker page from the console

---

## 5. Tournament
Bracket-style slot tournament; viewers enter and battle round by round.

1. Console → **Tournament** → **Create** → **Open Registration** → **Start**
2. Run matches, then **Cancel / Complete**

**Chat:** `!sr <slot>` (drawn participants)
**View:** console / admin

---

## OBS Overlay Sources
Add these as **Browser Sources** (background transparent, 1600×900 safe):

- `/overlay/bonus-bingo`
- `/overlay/chat-vs-streamer`
- `/overlay/climb-the-ladder`
- `/overlay/viewer-picker` *(random viewer highlight)*

Each polls the backend every ~3s and updates live.

---

## Go-Live Checklist
- [ ] Console loads, **Connect Discord** works
- [ ] Kick listener connected (Render greek-bingo log: `[kick-chat] connected`)
- [ ] Overlay(s) added to OBS
- [ ] Ran a **test round** (`!join` / `!win chat`) to confirm chat lands

---

*GreekGodBerry · HellCatCoins are entertainment-only virtual points — no real-world value.*