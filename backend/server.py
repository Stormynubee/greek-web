"""GreekGodBerry Community Platform — FastAPI backend."""
from __future__ import annotations

import os
import time
import logging
import secrets
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from models import User, UserPublic, LedgerEntry, Reward, StreamGame, GameEntry, utcnow

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ----- Config -----
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
DISCORD_CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
DISCORD_CLIENT_SECRET = os.environ["DISCORD_CLIENT_SECRET"]
DISCORD_REDIRECT_URI = os.environ["DISCORD_REDIRECT_URI"]
FRONTEND_URL = os.environ["FRONTEND_URL"]
LOCKLY_API_BASE = os.environ["LOCKLY_API_BASE"]
LOCKLY_API_KEY = os.environ["LOCKLY_API_KEY"]
JWT_SECRET = os.environ["JWT_SECRET"]
OWNER_EMAIL = os.environ["OWNER_EMAIL"]

JWT_ALG = "HS256"
JWT_TTL_DAYS = 14
SESSION_COOKIE = "ggb_session"

# ----- DB -----
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# ----- App -----
app = FastAPI(title="GreekGodBerry API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ggb")

# ================= Lockly leaderboard cache =================
_lockly_cache: dict[str, tuple[float, dict]] = {}
LOCKLY_TTL = 60  # seconds


async def _fetch_lockly(kind: str) -> dict:
    now = time.time()
    cached = _lockly_cache.get(kind)
    if cached and now - cached[0] < LOCKLY_TTL:
        return cached[1]
    async with httpx.AsyncClient(timeout=10.0) as hc:
        r = await hc.get(
            f"{LOCKLY_API_BASE}/leaderboard",
            params={"type": kind},
            headers={"x-streamer-api-key": LOCKLY_API_KEY},
        )
    if r.status_code != 200:
        # serve stale if we have it
        if cached:
            return cached[1]
        raise HTTPException(502, f"Lockly upstream error: {r.status_code}")
    data = r.json()
    _lockly_cache[kind] = (now, data)
    return data


# ================= Auth helpers =================
def _make_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_TTL_DAYS * 86400,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode_jwt(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


async def _current_user(ggb_session: Optional[str] = Cookie(default=None)) -> User:
    if not ggb_session:
        raise HTTPException(401, "Not authenticated")
    user_id = _decode_jwt(ggb_session)
    if not user_id:
        raise HTTPException(401, "Invalid session")
    doc = await db.users.find_one({"discord_id": user_id})
    user = User.from_mongo(doc)
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def _require_owner(user: User = Depends(_current_user)) -> User:
    if user.role != "owner":
        raise HTTPException(403, "Owner only")
    return user


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id or "",
        discord_id=user.discord_id,
        username=user.username,
        avatar_url=user.avatar_url,
        role=user.role,
        points_balance=user.points_balance,
    )


# ================= Ledger =================
async def _apply_ledger(user: User, delta: int, reason: str, ref: Optional[str] = None,
                        idempotency_key: Optional[str] = None) -> LedgerEntry:
    if idempotency_key:
        existing = await db.ledger.find_one({"idempotency_key": idempotency_key})
        if existing:
            return LedgerEntry.from_mongo(existing)
    new_balance = user.points_balance + delta
    if new_balance < 0:
        raise HTTPException(400, "Insufficient points")
    entry = LedgerEntry(
        user_id=user.discord_id,
        delta=delta,
        balance_after=new_balance,
        reason=reason,
        ref=ref,
        idempotency_key=idempotency_key,
    )
    await db.ledger.insert_one(entry.to_mongo())
    await db.users.update_one(
        {"discord_id": user.discord_id},
        {"$set": {"points_balance": new_balance, "updated_at": utcnow().isoformat()}},
    )
    user.points_balance = new_balance
    return entry


# ================= Startup =================
@app.on_event("startup")
async def startup():
    # Ensure indexes
    await db.users.create_index("discord_id", unique=True)
    await db.users.create_index("email")
    await db.ledger.create_index("user_id")
    await db.ledger.create_index("idempotency_key", unique=True, sparse=True)
    # Seed default rewards if empty
    if await db.rewards.count_documents({}) == 0:
        seeds = [
            Reward(title="GreekGodBerry Sticker Pack", description="Limited samurai sticker set.",
                   cost=500, stock=50, image_url="/assets/samurai-coin.png"),
            Reward(title="Discord VIP Role — 30 days", description="Stand out in chat with a VIP tag.",
                   cost=1500, stock=-1, image_url="/assets/samurai-coin.png"),
            Reward(title="Shoutout on Stream", description="Get a personal shoutout on the next stream.",
                   cost=3000, stock=10, image_url="/assets/samurai-coin.png"),
            Reward(title="$25 Gift Card", description="Digital gift card of your choice.",
                   cost=25000, stock=5, image_url="/assets/samurai-coin.png"),
        ]
        for r in seeds:
            await db.rewards.insert_one(r.to_mongo())
    log.info("Startup complete. Owner email: %s", OWNER_EMAIL)


@app.on_event("shutdown")
async def shutdown():
    client.close()


# ================= Routes =================
@api.get("/")
async def root():
    return {"service": "ggb-api", "status": "ok"}


# ---------- Discord OAuth ----------
@api.get("/auth/discord/login")
async def discord_login():
    state = secrets.token_urlsafe(16)
    scope = "identify email"
    url = (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={DISCORD_CLIENT_ID}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code&scope={scope.replace(' ', '%20')}"
        f"&state={state}&prompt=consent"
    )
    return {"url": url}


@api.get("/auth/discord/callback")
async def discord_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error or not code:
        return RedirectResponse(f"{FRONTEND_URL}/?auth=error")

    # exchange code
    async with httpx.AsyncClient(timeout=10.0) as hc:
        tok = await hc.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if tok.status_code != 200:
            log.error("Discord token exchange failed: %s %s", tok.status_code, tok.text)
            return RedirectResponse(f"{FRONTEND_URL}/?auth=error")
        access_token = tok.json()["access_token"]

        me = await hc.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return RedirectResponse(f"{FRONTEND_URL}/?auth=error")
        du = me.json()

    discord_id = du["id"]
    username = du.get("global_name") or du.get("username") or "Anon"
    email = du.get("email")
    avatar_hash = du.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash else None
    )

    # upsert user, owner-elevate if email matches
    is_owner = email and email.lower() == OWNER_EMAIL.lower()
    role = "owner" if is_owner else "viewer"

    existing = await db.users.find_one({"discord_id": discord_id})
    if existing:
        update = {
            "username": username,
            "email": email,
            "avatar_url": avatar_url,
            "updated_at": utcnow().isoformat(),
        }
        # elevate only, never demote silently
        if is_owner and existing.get("role") != "owner":
            update["role"] = "owner"
        await db.users.update_one({"discord_id": discord_id}, {"$set": update})
    else:
        user = User(
            discord_id=discord_id,
            username=username,
            email=email,
            avatar_url=avatar_url,
            role=role,
            points_balance=100,  # signup bonus
        )
        await db.users.insert_one(user.to_mongo())
        # log signup bonus in ledger (best-effort)
        entry = LedgerEntry(
            user_id=discord_id, delta=100, balance_after=100,
            reason="signup_bonus", idempotency_key=f"signup_{discord_id}",
        )
        try:
            await db.ledger.insert_one(entry.to_mongo())
        except Exception:
            pass

    token = _make_jwt(discord_id)
    resp = RedirectResponse(f"{FRONTEND_URL}/?auth=success")
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=JWT_TTL_DAYS * 86400,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return resp


@api.get("/auth/me")
async def auth_me(user: User = Depends(_current_user)):
    return _public(user)


@api.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ---------- Leaderboard ----------
@api.get("/leaderboard")
async def leaderboard(type: str = "monthly", mask: bool = True):
    if type not in {"daily", "weekly", "monthly"}:
        raise HTTPException(400, "type must be daily|weekly|monthly")
    data = await _fetch_lockly(type)
    ro = data.get("responseObject") or {}
    rankings = ro.get("rankings") or []
    out = []
    for i, row in enumerate(rankings):
        u = row.get("user") or {}
        name = u.get("name") or "Anon"
        if mask:
            # anon mask: first 3 chars + ***
            name = (name[:3] + "***") if len(name) > 3 else "***"
        out.append({
            "rank": i + 1,
            "name": name,
            "wagered": round(float(row.get("wagerAmount") or 0), 2),
            "bets": int(row.get("betCount") or 0),
        })
    return {
        "type": ro.get("type", type),
        "from": ro.get("from"),
        "total_users": ro.get("totalUsers", len(out)),
        "total_wagered": round(float(ro.get("totalWagered") or 0), 2),
        "rankings": out,
        "cached_ttl_seconds": LOCKLY_TTL,
    }


# ---------- Points ----------
@api.get("/points/me")
async def points_me(user: User = Depends(_current_user)):
    return {"balance": user.points_balance, "discord_id": user.discord_id}


@api.get("/points/ledger")
async def points_ledger(user: User = Depends(_current_user), limit: int = 50):
    cur = db.ledger.find({"user_id": user.discord_id}).sort("created_at", -1).limit(limit)
    docs = await cur.to_list(length=limit)
    out = []
    for d in docs:
        out.append({
            "delta": d["delta"],
            "balance_after": d["balance_after"],
            "reason": d["reason"],
            "ref": d.get("ref"),
            "created_at": d["created_at"],
        })
    return {"entries": out}


# ---------- Store ----------
@api.get("/store/rewards")
async def list_rewards():
    docs = await db.rewards.find({"active": True}).to_list(length=100)
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "title": d["title"],
            "description": d["description"],
            "cost": d["cost"],
            "stock": d["stock"],
            "image_url": d.get("image_url"),
        })
    return {"rewards": out}


class RedeemBody(BaseModel):
    reward_id: str
    idempotency_key: Optional[str] = None


@api.post("/store/redeem")
async def redeem(body: RedeemBody, user: User = Depends(_current_user)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(body.reward_id)
    except Exception:
        raise HTTPException(400, "Invalid reward id")
    reward_doc = await db.rewards.find_one({"_id": oid, "active": True})
    if not reward_doc:
        raise HTTPException(404, "Reward not found")
    if reward_doc["stock"] == 0:
        raise HTTPException(400, "Out of stock")
    if user.points_balance < reward_doc["cost"]:
        raise HTTPException(400, "Insufficient points")

    entry = await _apply_ledger(
        user, -reward_doc["cost"], "store_redeem",
        ref=body.reward_id, idempotency_key=body.idempotency_key,
    )
    if reward_doc["stock"] > 0:
        await db.rewards.update_one({"_id": oid}, {"$inc": {"stock": -1}})
    return {
        "ok": True,
        "reward": reward_doc["title"],
        "cost": reward_doc["cost"],
        "balance_after": entry.balance_after,
    }


# ---------- Stream Games ----------
@api.get("/games")
async def list_games():
    docs = await db.games.find({}).sort("created_at", -1).to_list(length=50)
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "title": d["title"],
            "kind": d["kind"],
            "status": d["status"],
            "entry_cost": d.get("entry_cost", 0),
            "reward_pool": d.get("reward_pool", 0),
            "prompt": d.get("prompt"),
            "options": d.get("options", []),
            "winning_option": d.get("winning_option"),
        })
    return {"games": out}


class GameCreate(BaseModel):
    title: str
    kind: str
    prompt: Optional[str] = None
    options: list[str] = []
    entry_cost: int = 0
    reward_pool: int = 0


@api.post("/admin/games")
async def create_game(body: GameCreate, _: User = Depends(_require_owner)):
    game = StreamGame(
        title=body.title, kind=body.kind, prompt=body.prompt,
        options=body.options, entry_cost=body.entry_cost, reward_pool=body.reward_pool,
    )
    res = await db.games.insert_one(game.to_mongo())
    return {"id": str(res.inserted_id)}


class GameResolve(BaseModel):
    winning_option: Optional[str] = None


@api.post("/admin/games/{game_id}/resolve")
async def resolve_game(game_id: str, body: GameResolve, _: User = Depends(_require_owner)):
    from bson import ObjectId as _OID
    oid = _OID(game_id)
    game_doc = await db.games.find_one({"_id": oid})
    if not game_doc:
        raise HTTPException(404, "Game not found")
    if game_doc["status"] == "resolved":
        raise HTTPException(400, "Already resolved")

    # find winners
    winners_q = {"game_id": game_id}
    if body.winning_option is not None:
        winners_q["choice"] = body.winning_option
    winner_entries = await db.game_entries.find(winners_q).to_list(length=10000)
    pool = int(game_doc.get("reward_pool") or 0)
    winners_count = len(winner_entries)
    per_winner = (pool // winners_count) if winners_count > 0 else 0

    # payout
    for we in winner_entries:
        doc_u = await db.users.find_one({"discord_id": we["user_id"]})
        u = User.from_mongo(doc_u)
        if u and per_winner > 0:
            await _apply_ledger(u, per_winner, "game_reward", ref=game_id,
                                idempotency_key=f"gp_{game_id}_{we['user_id']}")

    await db.games.update_one({"_id": oid}, {"$set": {
        "status": "resolved",
        "winning_option": body.winning_option,
        "resolved_at": utcnow().isoformat(),
    }})
    return {"ok": True, "winners": winners_count, "per_winner": per_winner}


class GameJoin(BaseModel):
    game_id: str
    choice: Optional[str] = None


@api.post("/games/join")
async def join_game(body: GameJoin, user: User = Depends(_current_user)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(body.game_id)
    except Exception:
        raise HTTPException(400, "Invalid game id")
    game_doc = await db.games.find_one({"_id": oid})
    if not game_doc:
        raise HTTPException(404, "Game not found")
    if game_doc["status"] != "open":
        raise HTTPException(400, "Game closed")

    # one entry per user per game
    dup = await db.game_entries.find_one({"game_id": body.game_id, "user_id": user.discord_id})
    if dup:
        raise HTTPException(400, "Already joined")

    cost = int(game_doc.get("entry_cost") or 0)
    if cost > 0:
        await _apply_ledger(user, -cost, "game_entry",
                            ref=body.game_id,
                            idempotency_key=f"ge_{body.game_id}_{user.discord_id}")

    entry = GameEntry(game_id=body.game_id, user_id=user.discord_id,
                      choice=body.choice, stake=cost)
    await db.game_entries.insert_one(entry.to_mongo())
    return {"ok": True, "balance_after": user.points_balance}


# ---------- Admin ----------
class RewardCreate(BaseModel):
    title: str
    description: str
    cost: int
    stock: int = -1
    image_url: Optional[str] = None


@api.post("/admin/rewards")
async def admin_create_reward(body: RewardCreate, _: User = Depends(_require_owner)):
    r = Reward(**body.model_dump())
    res = await db.rewards.insert_one(r.to_mongo())
    return {"id": str(res.inserted_id)}


class GrantBody(BaseModel):
    discord_id: str
    delta: int
    reason: str = "admin_grant"


@api.post("/admin/points/grant")
async def admin_grant(body: GrantBody, _: User = Depends(_require_owner)):
    doc = await db.users.find_one({"discord_id": body.discord_id})
    u = User.from_mongo(doc)
    if not u:
        raise HTTPException(404, "User not found")
    entry = await _apply_ledger(u, body.delta, body.reason)
    return {"ok": True, "balance_after": entry.balance_after}


@api.get("/admin/users")
async def admin_users(_: User = Depends(_require_owner)):
    docs = await db.users.find({}).sort("created_at", -1).to_list(length=500)
    out = []
    for d in docs:
        out.append({
            "discord_id": d["discord_id"],
            "username": d["username"],
            "email": d.get("email"),
            "role": d["role"],
            "points_balance": d["points_balance"],
        })
    return {"users": out}


# ---------- Mount ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
