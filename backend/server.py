"""GreekGodBerry Community Platform — FastAPI backend."""
from __future__ import annotations

import os
import time
import logging
import secrets
import hmac
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import random
from urllib.parse import urlencode

import bcrypt
import httpx
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Cookie
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

from models import (
    User, UserPublic, LedgerEntry, Reward, StreamGame, GameEntry,
    Giveaway, GiveawayEntry, CustomLeaderboardEntry, LiveStatus,
    AdminAccount, utcnow,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            f"Copy {ROOT_DIR / '.env.example'} to {ROOT_DIR / '.env'} and configure it."
        )
    return value


APP_ENV = os.getenv("APP_ENV", "development").lower()
MONGO_URL = _required_env("MONGO_URL")
DB_NAME = _required_env("DB_NAME")
DISCORD_CLIENT_ID = _required_env("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = _required_env("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = _required_env("DISCORD_REDIRECT_URI")
FRONTEND_URL = _required_env("FRONTEND_URL").rstrip("/")
LOCKLY_API_BASE = _required_env("LOCKLY_API_BASE").rstrip("/")
LOCKLY_API_KEY = _required_env("LOCKLY_API_KEY")
JWT_SECRET = _required_env("JWT_SECRET")
ADMIN_JWT_SECRET = _required_env("ADMIN_JWT_SECRET")
OWNER_EMAIL = _required_env("OWNER_EMAIL")
ADMIN_USERNAME = _required_env("ADMIN_USERNAME")
ADMIN_PASSWORD = _required_env("ADMIN_PASSWORD")

CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", FRONTEND_URL).split(",")
    if origin.strip()
]
if not CORS_ORIGINS or any("*" in origin for origin in CORS_ORIGINS):
    raise RuntimeError(
        "CORS_ORIGINS must contain one or more explicit origins; "
        "wildcard origins are not allowed with credentialed cookies."
    )

COOKIE_SECURE = os.getenv(
    "COOKIE_SECURE", "true" if APP_ENV in {"production", "staging"} else "false"
).lower() == "true"
COOKIE_SAMESITE = os.getenv(
    "COOKIE_SAMESITE", "none" if COOKIE_SECURE else "lax"
).lower()
if COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("COOKIE_SAMESITE must be lax, strict, or none.")
if COOKIE_SAMESITE == "none" and not COOKIE_SECURE:
    raise RuntimeError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true.")
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"

JWT_ALG = "HS256"
JWT_TTL_DAYS = 14
ADMIN_TTL_HOURS = 12
SESSION_COOKIE = "ggb_session"
ADMIN_COOKIE = "ggb_admin"
OAUTH_STATE_COOKIE = "ggb_oauth_state"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="GreekGodBerry API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ggb")


async def _run_transaction(callback):
    async with await client.start_session() as session:
        return await session.with_transaction(callback)

# ================= Lockly cache =================
_lockly_cache: dict[str, tuple[float, dict]] = {}
LOCKLY_TTL = 60


async def _fetch_lockly(kind: str) -> dict:
    now = time.time()
    cached = _lockly_cache.get(kind)
    if cached and now - cached[0] < LOCKLY_TTL:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            r = await hc.get(
                f"{LOCKLY_API_BASE}/leaderboard",
                params={"type": kind},
                headers={"x-streamer-api-key": LOCKLY_API_KEY},
            )
    except httpx.HTTPError as exc:
        log.warning("Lockly leaderboard request failed: %s", exc)
        if cached:
            return cached[1]
        return {"responseObject": {"type": kind, "rankings": [], "from": None}, "upstream_unavailable": True}
    if r.status_code != 200:
        if cached:
            return cached[1]
        log.warning("Lockly leaderboard returned status %s", r.status_code)
        return {"responseObject": {"type": kind, "rankings": [], "from": None}, "upstream_unavailable": True}
    data = r.json()
    _lockly_cache[kind] = (now, data)
    return data


# ================= JWT helpers =================
def _make_jwt(sub: str, secret: str, ttl_seconds: int) -> str:
    return jwt.encode(
        {"sub": sub, "iat": int(time.time()), "exp": int(time.time()) + ttl_seconds},
        secret, algorithm=JWT_ALG,
    )


def _decode_jwt(token: str, secret: str) -> Optional[str]:
    try:
        return jwt.decode(token, secret, algorithms=[JWT_ALG]).get("sub")
    except jwt.PyJWTError:
        return None


async def _current_user(ggb_session: Optional[str] = Cookie(default=None)) -> User:
    if not ggb_session:
        raise HTTPException(401, "Not authenticated")
    sub = _decode_jwt(ggb_session, JWT_SECRET)
    if not sub:
        raise HTTPException(401, "Invalid session")
    doc = await db.users.find_one({"discord_id": sub})
    user = User.from_mongo(doc)
    if not user:
        raise HTTPException(401, "User not found")
    return user


async def _require_admin(ggb_admin: Optional[str] = Cookie(default=None)) -> dict:
    """Admin session (username/password) — separate from Discord."""
    if not ggb_admin:
        raise HTTPException(401, "Admin session required")
    sub = _decode_jwt(ggb_admin, ADMIN_JWT_SECRET)
    if not sub or sub != ADMIN_USERNAME:
        raise HTTPException(401, "Invalid admin session")
    return {"username": sub}


async def _require_owner_or_admin(
    ggb_session: Optional[str] = Cookie(default=None),
    ggb_admin: Optional[str] = Cookie(default=None),
) -> dict:
    """Either the Discord-owner OR the custom-admin can access."""
    if ggb_admin:
        sub = _decode_jwt(ggb_admin, ADMIN_JWT_SECRET)
        if sub == ADMIN_USERNAME:
            return {"kind": "admin", "username": sub}
    if ggb_session:
        sub = _decode_jwt(ggb_session, JWT_SECRET)
        if sub:
            doc = await db.users.find_one({"discord_id": sub})
            user = User.from_mongo(doc)
            if user and user.role == "owner":
                return {"kind": "owner", "user": user}
    raise HTTPException(403, "Owner or admin required")


def _client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _public(user: User) -> UserPublic:
    return UserPublic(
        id=user.id or "", discord_id=user.discord_id, username=user.username,
        avatar_url=user.avatar_url, role=user.role, points_balance=user.points_balance,
    )


# ================= Ledger =================
async def _apply_ledger_in_transaction(
    session,
    user: User,
    delta: int,
    reason: str,
    ref: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> LedgerEntry:
    if idempotency_key:
        existing = await db.ledger.find_one(
            {"idempotency_key": idempotency_key}, session=session
        )
        if existing:
            return LedgerEntry.from_mongo(existing)

    balance_query = {"discord_id": user.discord_id}
    if delta < 0:
        balance_query["points_balance"] = {"$gte": abs(delta)}
    updated = await db.users.update_one(
        balance_query,
        {"$inc": {"points_balance": delta}, "$set": {"updated_at": utcnow().isoformat()}},
        session=session,
    )
    if updated.matched_count != 1:
        raise HTTPException(400, "Insufficient points")

    fresh_user = await db.users.find_one({"discord_id": user.discord_id}, session=session)
    new_balance = int(fresh_user["points_balance"])
    entry = LedgerEntry(
        user_id=user.discord_id, delta=delta, balance_after=new_balance,
        reason=reason, ref=ref, idempotency_key=idempotency_key,
    )
    await db.ledger.insert_one(entry.to_mongo(), session=session)
    user.points_balance = new_balance
    return entry


async def _apply_ledger(
    user: User,
    delta: int,
    reason: str,
    ref: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> LedgerEntry:
    async def apply(session):
        return await _apply_ledger_in_transaction(
            session, user, delta, reason, ref, idempotency_key
        )

    return await _run_transaction(apply)


# ================= Brute force helper =================
async def _check_bruteforce(identifier: str) -> None:
    """5 failed attempts in last 15 min → lockout."""
    since = time.time() - 900
    count = await db.admin_login_attempts.count_documents({
        "identifier": identifier, "success": False, "ts": {"$gte": since},
    })
    if count >= 5:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")


async def _log_attempt(identifier: str, success: bool) -> None:
    await db.admin_login_attempts.insert_one({
        "identifier": identifier, "success": success, "ts": time.time(),
    })
    if success:
        # clear old failures on success
        await db.admin_login_attempts.delete_many({"identifier": identifier, "success": False})


# ================= Startup =================
@app.on_event("startup")
async def startup():
    await db.command("ping")
    await db.users.create_index("discord_id", unique=True)
    await db.users.create_index("email")
    await db.ledger.create_index([("user_id", 1), ("created_at", -1)])
    await db.ledger.create_index("idempotency_key", unique=True, sparse=True)
    await db.admin_accounts.create_index("username", unique=True)
    await db.admin_login_attempts.create_index("identifier")
    await db.admin_login_attempts.create_index("ts")
    await db.giveaway_entries.create_index([("giveaway_id", 1), ("user_id", 1)], unique=True)
    await db.game_entries.create_index([("game_id", 1), ("user_id", 1)], unique=True)
    await db.game_entries.create_index([("game_id", 1), ("choice", 1)])
    await db.rewards.create_index([("active", 1), ("cost", 1)])
    await db.games.create_index([("status", 1), ("created_at", -1)])
    await db.giveaways.create_index([("status", 1), ("created_at", -1)])

    # Seed rewards (matching point shop screenshot vibe)
    if await db.rewards.count_documents({}) == 0:
        seeds = [
            Reward(title="$5 Rainbet Tip", description="Redeemer claims a $5 tip to their Rainbet account.",
                   cost=750, stock=-1, category="bonus", requires="Rainbet username"),
            Reward(title="$100 BONUS BUY - Keep 10% of payout",
                   description="Redeemer picks slots & keeps 10% of whatever it pays.",
                   cost=1750, stock=-1, category="custom", requires="Rainbet username"),
            Reward(title="$200 BONUS BUY - Keep 10% of payout",
                   description="Redeemer picks slots & keeps 10% of whatever it pays (MUST BE ON CODE CAM TO CLAIM)",
                   cost=2500, stock=-1, category="custom", requires="Rainbet username"),
            Reward(title="$20 Rainbet Tip",
                   description="Redeemer claims a $20 tip to their Rainbet account - (MUST BE ON CODE CAM w/ LIFETIME MIN. $5,000 WAGERED TO CLAIM).",
                   cost=2500, stock=-1, category="custom", requires="Rainbet username"),
            Reward(title="BEST OF 3 - $100 BONUS BUY - Keep 10% of payout",
                   description="Redeemer picks slots & keeps 10% of whatever slot pays the most (MUST BE ON CODE CAM TO CLAIM)",
                   cost=3250, stock=-1, category="custom", requires="Rainbet username"),
            Reward(title="$1,000 50/50 Split Bonus Hunt with Cam!",
                   description="Hop on discord chat w/Cam and play - decide what we spin into and cash out half of what the hunt pays! (MUST BE ON CODE CAM w/ LIFETIME MIN. $10,000 WAGERED TO CLAIM)",
                   cost=69000, stock=-1, category="custom", requires="Rainbet username, Discord linked"),
        ]
        for r in seeds:
            await db.rewards.insert_one(r.to_mongo())

    # Seed admin account
    existing_admin = await db.admin_accounts.find_one({"username": ADMIN_USERNAME})
    hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    if not existing_admin:
        await db.admin_accounts.insert_one(AdminAccount(
            username=ADMIN_USERNAME, password_hash=hashed,
        ).to_mongo())
        log.info("Seeded admin account: %s", ADMIN_USERNAME)
    elif not bcrypt.checkpw(ADMIN_PASSWORD.encode("utf-8"), existing_admin["password_hash"].encode("utf-8")):
        await db.admin_accounts.update_one(
            {"username": ADMIN_USERNAME},
            {"$set": {"password_hash": hashed, "updated_at": utcnow().isoformat()}},
        )
        log.info("Updated admin password from .env")

    # Seed default live status if missing
    if await db.live_status.count_documents({}) == 0:
        await db.live_status.insert_one(LiveStatus().to_mongo())

    log.info("Startup complete. Owner email: %s", OWNER_EMAIL)


@app.on_event("shutdown")
async def shutdown():
    client.close()


# ================= Routes =================
@api.get("/")
async def root():
    return {"service": "ggb-api", "status": "ok"}


@api.get("/health")
async def health():
    try:
        await db.command("ping")
    except Exception as exc:
        log.error("Health check database ping failed: %s", exc)
        raise HTTPException(503, "Database unavailable")
    return {"service": "ggb-api", "status": "ok", "database": "ok"}


# ---------- Discord OAuth ----------
@api.get("/auth/discord/login")
async def discord_login(response: Response):
    state = secrets.token_urlsafe(16)
    url = "https://discord.com/api/oauth2/authorize?" + urlencode(
        {
            "client_id": DISCORD_CLIENT_ID,
            "redirect_uri": DISCORD_REDIRECT_URI,
            "response_type": "code",
            "scope": "identify email",
            "state": state,
            "prompt": "consent",
        }
    )
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/api/auth/discord",
    )
    return {"url": url}


@api.get("/auth/discord/callback")
async def discord_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    oauth_state: Optional[str] = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
):
    def oauth_error():
        response = RedirectResponse(f"{FRONTEND_URL}/?auth=error")
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/discord")
        return response

    if error or not code:
        return oauth_error()
    if not state or not oauth_state or not hmac.compare_digest(state, oauth_state):
        log.warning("Rejected Discord OAuth callback with invalid state")
        return oauth_error()
    async with httpx.AsyncClient(timeout=10.0) as hc:
        tok = await hc.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code", "code": code, "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if tok.status_code != 200:
            log.error("Discord token exchange failed: %s", tok.text)
            return oauth_error()
        access_token = tok.json()["access_token"]
        me = await hc.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return oauth_error()
        du = me.json()

    discord_id = du["id"]
    username = du.get("global_name") or du.get("username") or "Anon"
    email = du.get("email")
    avatar_hash = du.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash else None
    )
    is_owner = email and email.lower() == OWNER_EMAIL.lower()
    existing = await db.users.find_one({"discord_id": discord_id})
    if existing:
        update = {"username": username, "email": email, "avatar_url": avatar_url,
                  "updated_at": utcnow().isoformat()}
        if is_owner and existing.get("role") != "owner":
            update["role"] = "owner"
        await db.users.update_one({"discord_id": discord_id}, {"$set": update})
    else:
        user = User(
            discord_id=discord_id, username=username, email=email, avatar_url=avatar_url,
            role="owner" if is_owner else "viewer", points_balance=0,
        )
        try:
            async def create_user_with_bonus(session):
                await db.users.insert_one(user.to_mongo(), session=session)
                await _apply_ledger_in_transaction(
                    session,
                    user,
                    100,
                    "signup_bonus",
                    idempotency_key=f"signup_{discord_id}",
                )

            await _run_transaction(create_user_with_bonus)
        except DuplicateKeyError:
            log.info("Discord user was created concurrently: %s", discord_id)

    token = _make_jwt(discord_id, JWT_SECRET, JWT_TTL_DAYS * 86400)
    resp = RedirectResponse(f"{FRONTEND_URL}/?auth=success")
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=JWT_TTL_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/discord")
    return resp


@api.get("/auth/me")
async def auth_me(user: User = Depends(_current_user)):
    return _public(user)


@api.post("/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ---------- ADMIN AUTH (custom username/password) ----------
class AdminLoginBody(BaseModel):
    username: str
    password: str


@api.post("/admin/login")
async def admin_login(body: AdminLoginBody, request: Request, response: Response):
    identifiers = [
        f"ip:{_client_ip(request)}",
        f"user:{body.username.lower()}",
    ]
    for identifier in identifiers:
        await _check_bruteforce(identifier)

    doc = await db.admin_accounts.find_one({"username": body.username})
    if not doc or not bcrypt.checkpw(body.password.encode("utf-8"),
                                     doc["password_hash"].encode("utf-8")):
        for identifier in identifiers:
            await _log_attempt(identifier, False)
        raise HTTPException(401, "Invalid credentials")

    for identifier in identifiers:
        await _log_attempt(identifier, True)
    token = _make_jwt(body.username, ADMIN_JWT_SECRET, ADMIN_TTL_HOURS * 3600)
    response.set_cookie(
        ADMIN_COOKIE,
        token,
        max_age=ADMIN_TTL_HOURS * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return {"ok": True, "username": body.username}


@api.get("/admin/me")
async def admin_me(admin: dict = Depends(_require_admin)):
    return {"username": admin["username"], "kind": "admin"}


@api.post("/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"ok": True}


# ---------- Leaderboard (Lockly + custom merge) ----------
@api.get("/leaderboard")
async def leaderboard(type: str = "monthly", mask: bool = False):
    if type not in {"daily", "weekly", "monthly"}:
        raise HTTPException(400, "type must be daily|weekly|monthly")
    data = await _fetch_lockly(type)
    ro = data.get("responseObject") or {}
    lockly_rows = []
    for row in ro.get("rankings") or []:
        u = row.get("user") or {}
        name = u.get("name") or "Anon"
        lockly_rows.append({
            "name": (name[:3] + "***") if mask and len(name) > 3 else name,
            "wagered": round(float(row.get("wagerAmount") or 0), 2),
            "bets": int(row.get("betCount") or 0),
            "source": "lockly",
        })

    # merge with custom entries for the same board
    custom_docs = await db.custom_leaderboard.find({"board": type}).to_list(500)
    for d in custom_docs:
        lockly_rows.append({
            "name": d["display_name"],
            "wagered": round(float(d.get("wagered") or 0), 2),
            "bets": int(d.get("bets") or 0),
            "source": "custom",
        })

    lockly_rows.sort(key=lambda r: r["wagered"], reverse=True)
    for i, r in enumerate(lockly_rows):
        r["rank"] = i + 1
    return {
        "type": ro.get("type", type),
        "from": ro.get("from"),
        "total_users": len(lockly_rows),
        "total_wagered": round(sum(r["wagered"] for r in lockly_rows), 2),
        "rankings": lockly_rows,
        "cached_ttl_seconds": LOCKLY_TTL,
        "upstream_unavailable": bool(data.get("upstream_unavailable")),
    }


# ---------- Points ----------
@api.get("/points/me")
async def points_me(user: User = Depends(_current_user)):
    return {"balance": user.points_balance, "discord_id": user.discord_id}


@api.get("/points/ledger")
async def points_ledger(user: User = Depends(_current_user), limit: int = 50):
    docs = await db.ledger.find({"user_id": user.discord_id}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"entries": [{
        "delta": d["delta"], "balance_after": d["balance_after"],
        "reason": d["reason"], "ref": d.get("ref"), "created_at": d["created_at"],
    } for d in docs]}


@api.get("/points/redemptions")
async def points_redemptions(user: User = Depends(_current_user)):
    docs = await db.ledger.find({
        "user_id": user.discord_id, "reason": "store_redeem"
    }).sort("created_at", -1).limit(100).to_list(100)
    out = []
    for d in docs:
        reward_title = None
        if d.get("ref"):
            try:
                from bson import ObjectId as _OID
                rd = await db.rewards.find_one({"_id": _OID(d["ref"])})
                if rd:
                    reward_title = rd["title"]
            except Exception:
                pass
        out.append({
            "reward_title": reward_title or "Reward",
            "cost": -d["delta"],
            "created_at": d["created_at"],
        })
    return {"redemptions": out}


@api.get("/points/leaderboard")
async def points_leaderboard(limit: int = 20):
    docs = await db.users.find({"points_balance": {"$gt": 0}}) \
        .sort("points_balance", -1).limit(limit).to_list(limit)
    return {"leaderboard": [{
        "rank": i + 1, "username": d["username"], "avatar_url": d.get("avatar_url"),
        "points": d["points_balance"],
    } for i, d in enumerate(docs)]}


# ---------- Store ----------
@api.get("/store/rewards")
async def list_rewards():
    docs = await db.rewards.find({"active": True}).sort("cost", 1).to_list(200)
    return {"rewards": [{
        "id": str(d["_id"]), "title": d["title"], "description": d["description"],
        "cost": d["cost"], "stock": d["stock"], "image_url": d.get("image_url"),
        "category": d.get("category", "custom"), "requires": d.get("requires"),
    } for d in docs]}


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
    async def redeem_transaction(session):
        existing = None
        if body.idempotency_key:
            existing = await db.ledger.find_one(
                {
                    "idempotency_key": body.idempotency_key,
                    "user_id": user.discord_id,
                    "reason": "store_redeem",
                },
                session=session,
            )
        reward_doc = await db.rewards.find_one(
            {"_id": oid, "active": True}, session=session
        )
        if not reward_doc:
            if existing:
                return {
                    "ok": True,
                    "reward": "Reward",
                    "cost": -existing["delta"],
                    "balance_after": existing["balance_after"],
                }
            raise HTTPException(404, "Reward not found")
        if existing:
            return {
                "ok": True,
                "reward": reward_doc["title"],
                "cost": reward_doc["cost"],
                "balance_after": existing["balance_after"],
            }
        if reward_doc["stock"] == 0:
            raise HTTPException(400, "Out of stock")
        if reward_doc["stock"] > 0:
            stock_update = await db.rewards.update_one(
                {"_id": oid, "active": True, "stock": {"$gt": 0}},
                {"$inc": {"stock": -1}},
                session=session,
            )
            if stock_update.matched_count != 1:
                raise HTTPException(400, "Out of stock")
        entry = await _apply_ledger_in_transaction(
            session,
            user,
            -int(reward_doc["cost"]),
            "store_redeem",
            ref=body.reward_id,
            idempotency_key=body.idempotency_key,
        )
        return {
            "ok": True,
            "reward": reward_doc["title"],
            "cost": reward_doc["cost"],
            "balance_after": entry.balance_after,
        }

    return await _run_transaction(redeem_transaction)


# ---------- Games ----------
@api.get("/games")
async def list_games():
    docs = await db.games.find({}).sort("created_at", -1).to_list(50)
    return {"games": [{
        "id": str(d["_id"]), "title": d["title"], "kind": d["kind"], "status": d["status"],
        "entry_cost": d.get("entry_cost", 0), "reward_pool": d.get("reward_pool", 0),
        "prompt": d.get("prompt"), "options": d.get("options", []),
        "winning_option": d.get("winning_option"),
    } for d in docs]}


class GameCreate(BaseModel):
    title: str
    kind: str
    prompt: Optional[str] = None
    options: list[str] = []
    entry_cost: int = 0
    reward_pool: int = 0


@api.post("/admin/games")
async def create_game(body: GameCreate, _: dict = Depends(_require_owner_or_admin)):
    game = StreamGame(**body.model_dump())
    res = await db.games.insert_one(game.to_mongo())
    return {"id": str(res.inserted_id)}


class GameResolve(BaseModel):
    winning_option: Optional[str] = None


@api.post("/admin/games/{game_id}/resolve")
async def resolve_game(game_id: str, body: GameResolve, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(game_id)
    except Exception:
        raise HTTPException(400, "Invalid game id")
    async def resolve_transaction(session):
        game_doc = await db.games.find_one({"_id": oid}, session=session)
        if not game_doc:
            raise HTTPException(404, "Game not found")
        if game_doc["status"] == "resolved":
            raise HTTPException(400, "Already resolved")
        winners_q = {"game_id": game_id}
        if body.winning_option is not None:
            winners_q["choice"] = body.winning_option
        winner_entries = await db.game_entries.find(
            winners_q, session=session
        ).to_list(10000)
        pool = int(game_doc.get("reward_pool") or 0)
        per_winner = (pool // len(winner_entries)) if winner_entries else 0
        for we in winner_entries:
            u = User.from_mongo(
                await db.users.find_one(
                    {"discord_id": we["user_id"]}, session=session
                )
            )
            if u and per_winner > 0:
                await _apply_ledger_in_transaction(
                    session,
                    u,
                    per_winner,
                    "game_reward",
                    ref=game_id,
                    idempotency_key=f"gp_{game_id}_{we['user_id']}",
                )
        updated = await db.games.update_one(
            {"_id": oid, "status": "open"},
            {"$set": {
                "status": "resolved",
                "winning_option": body.winning_option,
                "resolved_at": utcnow().isoformat(),
            }},
            session=session,
        )
        if updated.matched_count != 1:
            raise HTTPException(400, "Game was resolved by another request")
        return {"ok": True, "winners": len(winner_entries), "per_winner": per_winner}

    return await _run_transaction(resolve_transaction)


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
    async def join_transaction(session):
        game_doc = await db.games.find_one({"_id": oid}, session=session)
        if not game_doc:
            raise HTTPException(404, "Game not found")
        if game_doc["status"] != "open":
            raise HTTPException(400, "Game closed")
        dup = await db.game_entries.find_one(
            {"game_id": body.game_id, "user_id": user.discord_id},
            session=session,
        )
        if dup:
            raise HTTPException(400, "Already joined")
        cost = int(game_doc.get("entry_cost") or 0)
        if cost > 0:
            await _apply_ledger_in_transaction(
                session,
                user,
                -cost,
                "game_entry",
                ref=body.game_id,
                idempotency_key=f"ge_{body.game_id}_{user.discord_id}",
            )
        entry = GameEntry(
            game_id=body.game_id,
            user_id=user.discord_id,
            choice=body.choice,
            stake=cost,
        )
        await db.game_entries.insert_one(entry.to_mongo(), session=session)

    try:
        await _run_transaction(join_transaction)
    except DuplicateKeyError:
        raise HTTPException(400, "Already joined")
    return {"ok": True, "balance_after": user.points_balance}


# ---------- GIVEAWAYS (public listing + entry, admin CRUD + draw) ----------
@api.get("/giveaways")
async def list_giveaways():
    docs = await db.giveaways.find({}).sort("created_at", -1).limit(50).to_list(50)
    out = []
    for d in docs:
        entries = await db.giveaway_entries.count_documents({"giveaway_id": str(d["_id"])})
        out.append({
            "id": str(d["_id"]), "title": d["title"], "description": d["description"],
            "prize": d["prize"], "image_url": d.get("image_url"),
            "max_winners": d.get("max_winners", 1),
            "status": d["status"], "ends_at": d.get("ends_at"),
            "winners": d.get("winners", []), "entries": entries,
            "created_at": d["created_at"],
        })
    return {"giveaways": out}


class GiveawayEnterBody(BaseModel):
    giveaway_id: str


@api.post("/giveaways/enter")
async def enter_giveaway(body: GiveawayEnterBody, user: User = Depends(_current_user)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(body.giveaway_id)
    except Exception:
        raise HTTPException(400, "Invalid id")
    g = await db.giveaways.find_one({"_id": oid})
    if not g:
        raise HTTPException(404, "Giveaway not found")
    if g["status"] != "open":
        raise HTTPException(400, "Giveaway closed")
    try:
        await db.giveaway_entries.insert_one(GiveawayEntry(
            giveaway_id=body.giveaway_id, user_id=user.discord_id, username=user.username,
        ).to_mongo())
    except DuplicateKeyError:
        raise HTTPException(400, "Already entered")
    total = await db.giveaway_entries.count_documents({"giveaway_id": body.giveaway_id})
    return {"ok": True, "entries": total}


class GiveawayCreate(BaseModel):
    title: str
    description: str
    prize: str
    image_url: Optional[str] = None
    max_winners: int = 1


@api.post("/admin/giveaways")
async def admin_create_giveaway(body: GiveawayCreate, _: dict = Depends(_require_owner_or_admin)):
    g = Giveaway(**body.model_dump())
    res = await db.giveaways.insert_one(g.to_mongo())
    return {"id": str(res.inserted_id)}


@api.post("/admin/giveaways/{gid}/draw")
async def admin_draw_giveaway(gid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(gid)
    except Exception:
        raise HTTPException(400, "Invalid giveaway id")
    g = await db.giveaways.find_one({"_id": oid})
    if not g:
        raise HTTPException(404, "Giveaway not found")
    if g["status"] == "drawn":
        raise HTTPException(400, "Already drawn")
    entries = await db.giveaway_entries.find({"giveaway_id": gid}).to_list(100000)
    if not entries:
        raise HTTPException(400, "No entries")
    n = min(g.get("max_winners", 1), len(entries))
    winners_e = random.sample(entries, n)
    winners = [{"discord_id": w["user_id"], "username": w["username"]} for w in winners_e]
    updated = await db.giveaways.update_one(
        {"_id": oid, "status": "open"},
        {"$set": {
            "status": "drawn", "drawn_at": utcnow().isoformat(),
            "winners": winners,
        }},
    )
    if updated.matched_count != 1:
        raise HTTPException(400, "Giveaway was already drawn or closed")
    return {"ok": True, "winners": winners}


@api.post("/admin/giveaways/{gid}/close")
async def admin_close_giveaway(gid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(gid)
    except Exception:
        raise HTTPException(400, "Invalid giveaway id")
    r = await db.giveaways.update_one({"_id": oid}, {"$set": {"status": "closed"}})
    if r.matched_count == 0:
        raise HTTPException(404, "Not found")
    return {"ok": True}


# ---------- Custom leaderboard entries (admin adds anyone manually) ----------
class CustomLBCreate(BaseModel):
    display_name: str
    wagered: float
    bets: int = 0
    board: str = "monthly"
    note: Optional[str] = None


@api.get("/admin/custom-leaderboard")
async def admin_list_custom_lb(_: dict = Depends(_require_owner_or_admin)):
    docs = await db.custom_leaderboard.find({}).sort("wagered", -1).to_list(500)
    return {"entries": [{
        "id": str(d["_id"]), "display_name": d["display_name"],
        "wagered": d["wagered"], "bets": d.get("bets", 0),
        "board": d.get("board", "monthly"), "note": d.get("note"),
    } for d in docs]}


@api.post("/admin/custom-leaderboard")
async def admin_add_custom_lb(body: CustomLBCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.board not in {"daily", "weekly", "monthly"}:
        raise HTTPException(400, "invalid board")
    entry = CustomLeaderboardEntry(**body.model_dump())
    res = await db.custom_leaderboard.insert_one(entry.to_mongo())
    return {"id": str(res.inserted_id)}


@api.delete("/admin/custom-leaderboard/{eid}")
async def admin_del_custom_lb(eid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(eid)
    except Exception:
        raise HTTPException(400, "Invalid entry id")
    result = await db.custom_leaderboard.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Entry not found")
    return {"ok": True}


# ---------- Rewards admin ----------
class RewardCreate(BaseModel):
    title: str
    description: str
    cost: int
    stock: int = -1
    image_url: Optional[str] = None
    category: str = "custom"
    requires: Optional[str] = None


@api.post("/admin/rewards")
async def admin_create_reward(body: RewardCreate, _: dict = Depends(_require_owner_or_admin)):
    r = Reward(**body.model_dump())
    res = await db.rewards.insert_one(r.to_mongo())
    return {"id": str(res.inserted_id)}


@api.delete("/admin/rewards/{rid}")
async def admin_delete_reward(rid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(rid)
    except Exception:
        raise HTTPException(400, "Invalid reward id")
    result = await db.rewards.update_one({"_id": oid}, {"$set": {"active": False}})
    if result.matched_count == 0:
        raise HTTPException(404, "Reward not found")
    return {"ok": True}


# ---------- Points grant ----------
class GrantBody(BaseModel):
    discord_id: str
    delta: int
    reason: str = "admin_grant"


@api.post("/admin/points/grant")
async def admin_grant(body: GrantBody, _: dict = Depends(_require_owner_or_admin)):
    u = User.from_mongo(await db.users.find_one({"discord_id": body.discord_id}))
    if not u:
        raise HTTPException(404, "User not found")
    entry = await _apply_ledger(u, body.delta, body.reason)
    return {"ok": True, "balance_after": entry.balance_after}


@api.get("/admin/users")
async def admin_users(_: dict = Depends(_require_owner_or_admin)):
    docs = await db.users.find({}).sort("created_at", -1).to_list(1000)
    return {"users": [{
        "discord_id": d["discord_id"], "username": d["username"], "email": d.get("email"),
        "role": d["role"], "points_balance": d["points_balance"],
    } for d in docs]}


# ---------- Live status (LIVE ON KICK widget) ----------
@api.get("/live")
async def get_live():
    doc = await db.live_status.find_one({})
    if not doc:
        return {"is_live": False, "platform": "kick", "url": "https://kick.com/greekgodberry"}
    return {
        "is_live": bool(doc.get("is_live", False)),
        "platform": doc.get("platform", "kick"),
        "title": doc.get("title"),
        "url": doc.get("url", "https://kick.com/greekgodberry"),
    }


class LiveUpdate(BaseModel):
    is_live: bool
    title: Optional[str] = None
    platform: str = "kick"
    url: Optional[str] = None


@api.post("/admin/live")
async def admin_set_live(body: LiveUpdate, _: dict = Depends(_require_owner_or_admin)):
    upd = {"is_live": body.is_live, "platform": body.platform, "updated_at": utcnow().isoformat()}
    if body.title is not None:
        upd["title"] = body.title
    if body.url is not None:
        upd["url"] = body.url
    await db.live_status.update_one({}, {"$set": upd}, upsert=True)
    return {"ok": True}


# ---------- Mount ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
