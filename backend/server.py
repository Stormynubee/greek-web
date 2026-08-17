"""GreekGodBerry Community Platform — FastAPI backend."""
from __future__ import annotations

import os
import time
import logging
import secrets
import hmac
import asyncio
import math
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse

import bcrypt
import httpx
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, Cookie
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

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


def _is_http_url(value: Optional[str]) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_https_url(value: Optional[str]) -> bool:
    return bool(value and urlparse(value).scheme == "https" and urlparse(value).netloc)


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

LOCKLY_STREAMER_BASE = "https://public-api.lockly.io/api/public/streamer"
PRODUCTION_ENVS = {"production", "staging"}
PLACEHOLDER_MARKERS = (
    "replace-with",
    "change-me",
    "your-",
    "example-secret",
    "example.com",
)


def _validate_production_configuration() -> None:
    if APP_ENV not in PRODUCTION_ENVS:
        return
    required_real_values = {
        "DISCORD_CLIENT_ID": DISCORD_CLIENT_ID,
        "DISCORD_CLIENT_SECRET": DISCORD_CLIENT_SECRET,
        "LOCKLY_API_KEY": LOCKLY_API_KEY,
        "JWT_SECRET": JWT_SECRET,
        "ADMIN_JWT_SECRET": ADMIN_JWT_SECRET,
        "OWNER_EMAIL": OWNER_EMAIL,
        "ADMIN_USERNAME": ADMIN_USERNAME,
        "ADMIN_PASSWORD": ADMIN_PASSWORD,
    }
    required_real_values.update({
        "MONGO_URL": MONGO_URL,
        "DISCORD_REDIRECT_URI": DISCORD_REDIRECT_URI,
        "FRONTEND_URL": FRONTEND_URL,
        "CORS_ORIGINS": ",".join(CORS_ORIGINS),
    })
    invalid = [
        name for name, value in required_real_values.items()
        if (
            any(marker in value.lower() for marker in PLACEHOLDER_MARKERS)
            or "localhost" in value.lower()
            or "<" in value
            or ">" in value
        )
    ]
    if invalid:
        raise RuntimeError(
            "Production configuration still contains placeholders for: "
            + ", ".join(invalid)
            + ". Rotate and provision real values before release."
        )
    if LOCKLY_API_BASE != LOCKLY_STREAMER_BASE:
        raise RuntimeError(
            f"LOCKLY_API_BASE must be exactly {LOCKLY_STREAMER_BASE} in production."
        )
    if FRONTEND_URL not in CORS_ORIGINS:
        raise RuntimeError("FRONTEND_URL must be included in CORS_ORIGINS in production.")
    if len(JWT_SECRET) < 32 or len(ADMIN_JWT_SECRET) < 32:
        raise RuntimeError("Production JWT secrets must each contain at least 32 characters.")
    if JWT_SECRET == ADMIN_JWT_SECRET:
        raise RuntimeError("JWT_SECRET and ADMIN_JWT_SECRET must be different in production.")
    if len(ADMIN_PASSWORD) < 12:
        raise RuntimeError("ADMIN_PASSWORD must contain at least 12 characters in production.")
    if (
        not _is_https_url(FRONTEND_URL)
        or not _is_https_url(DISCORD_REDIRECT_URI)
        or any(not _is_https_url(origin) for origin in CORS_ORIGINS)
    ):
        raise RuntimeError(
            "Production frontend, CORS, and Discord redirect URLs must use HTTPS."
        )
    if not COOKIE_SECURE or COOKIE_SAMESITE != "none":
        raise RuntimeError(
            "Production cookie configuration requires COOKIE_SECURE=true and "
            "COOKIE_SAMESITE=none."
        )

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
_validate_production_configuration()

JWT_ALG = "HS256"
JWT_TTL_DAYS = 14
ADMIN_TTL_HOURS = 12
SESSION_COOKIE = "ggb_session"
ADMIN_COOKIE = "ggb_admin"
OAUTH_STATE_COOKIE = "ggb_oauth_state"

client = AsyncIOMotorClient(
    MONGO_URL,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    maxPoolSize=50,
)
db = client[DB_NAME]

app = FastAPI(title="GreekGodBerry API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
log = logging.getLogger("ggb")

HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
HTTP_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        async with _http_client_lock:
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=HTTP_TIMEOUT,
                    limits=HTTP_LIMITS,
                )
    return _http_client


async def _close_http_client() -> None:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None


PUBLIC_CACHE_HEADERS = {
    "/api/live": "public, max-age=10, stale-while-revalidate=30",
    "/api/leaderboard": "public, max-age=60, stale-while-revalidate=120",
    "/api/store/rewards": "public, max-age=30, stale-while-revalidate=120",
    "/api/games": "public, max-age=15, stale-while-revalidate=60",
    "/api/giveaways": "public, max-age=15, stale-while-revalidate=60",
}


@app.middleware("http")
async def add_public_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code == 200:
        cache_control = PUBLIC_CACHE_HEADERS.get(request.url.path)
        if cache_control:
            if request.cookies.get(ADMIN_COOKIE):
                response.headers["Cache-Control"] = "private, no-store"
            else:
                response.headers.setdefault("Cache-Control", cache_control)
            response.headers.add_vary_header("Origin")
    return response


async def _run_transaction(callback):
    async with await client.start_session() as session:
        return await session.with_transaction(callback)

# ================= Lockly cache =================
_lockly_cache: dict[str, tuple[float, dict]] = {}
_lockly_locks: dict[str, asyncio.Lock] = {}
_lockly_locks_guard = asyncio.Lock()
_lockly_retry_at: dict[str, float] = {}
LOCKLY_TTL = 60
LOCKLY_LIMIT = 100
LOCKLY_MAX_RETRY_DELAY = 300
MAX_GIVEAWAY_WINNERS = 100


def _retry_after_seconds(value: Optional[str], now: Optional[float] = None) -> Optional[int]:
    if not value:
        return None
    try:
        seconds = float(value)
        if seconds >= 0:
            return min(math.ceil(seconds), LOCKLY_MAX_RETRY_DELAY)
    except (TypeError, ValueError):
        pass
    try:
        retry_at = parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None
    current = time.time() if now is None else now
    return min(max(0, math.ceil(retry_at - current)), LOCKLY_MAX_RETRY_DELAY)


async def _lockly_lock(kind: str) -> asyncio.Lock:
    async with _lockly_locks_guard:
        lock = _lockly_locks.get(kind)
        if lock is None:
            lock = asyncio.Lock()
            _lockly_locks[kind] = lock
        return lock


def _lockly_unavailable(kind: str, cached: Optional[dict] = None) -> dict:
    if cached:
        return {**cached, "upstream_unavailable": True}
    return {
        "responseObject": {"type": kind, "rankings": [], "from": None},
        "upstream_unavailable": True,
    }


async def _fetch_lockly(kind: str) -> dict:
    lock = await _lockly_lock(kind)
    async with lock:
        now = time.time()
        cached_entry = _lockly_cache.get(kind)
        if cached_entry and now - cached_entry[0] < LOCKLY_TTL:
            return cached_entry[1]

        cached = cached_entry[1] if cached_entry else None
        if _lockly_retry_at.get(kind, 0) > now:
            return _lockly_unavailable(kind, cached)
        try:
            hc = await _get_http_client()
            response = await hc.get(
                f"{LOCKLY_API_BASE}/leaderboard",
                params={"type": kind, "limit": LOCKLY_LIMIT},
                headers={"x-streamer-api-key": LOCKLY_API_KEY},
            )
            if response.status_code != 200:
                retry_after = response.headers.get("retry-after")
                retry_seconds = _retry_after_seconds(retry_after)
                if retry_seconds is None:
                    retry_seconds = 300 if response.status_code == 401 else 30
                _lockly_retry_at[kind] = now + retry_seconds
                log.warning(
                    "Lockly leaderboard returned status %s%s",
                    response.status_code,
                    f" (retry after {retry_after}s)" if retry_after else "",
                )
                return _lockly_unavailable(kind, cached)

            data = response.json()
            if not isinstance(data, dict) or data.get("success") is not True:
                raise ValueError("Lockly returned an unsuccessful response envelope")
            response_object = data.get("responseObject")
            if not isinstance(response_object, dict):
                raise ValueError("Lockly responseObject is missing")
            if not isinstance(response_object.get("rankings"), list):
                raise ValueError("Lockly rankings are missing")
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Lockly leaderboard request failed: %s", exc)
            _lockly_retry_at[kind] = now + 30
            return _lockly_unavailable(kind, cached)

        _lockly_retry_at.pop(kind, None)
        _lockly_cache[kind] = (time.time(), data)
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
    doc = await db.users.find_one(
        {"discord_id": sub},
        {
            "_id": 1, "discord_id": 1, "username": 1, "email": 1,
            "avatar_url": 1, "role": 1, "points_balance": 1,
            "created_at": 1, "updated_at": 1,
        },
    )
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
            doc = await db.users.find_one(
                {"discord_id": sub},
                {
                    "_id": 1, "discord_id": 1, "username": 1, "email": 1,
                    "avatar_url": 1, "role": 1, "points_balance": 1,
                    "created_at": 1, "updated_at": 1,
                },
            )
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
            if (
                existing.get("user_id") != user.discord_id
                or existing.get("reason") != reason
            ):
                raise HTTPException(409, "Idempotency key already belongs to another operation")
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

    fresh_user = await db.users.find_one(
        {"discord_id": user.discord_id},
        {"points_balance": 1},
        session=session,
    )
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
    await asyncio.gather(
        db.users.create_index("discord_id", unique=True),
        db.users.create_index("email"),
        db.users.create_index("points_balance"),
        db.ledger.create_index([("user_id", 1), ("created_at", -1)]),
        db.ledger.create_index("idempotency_key", unique=True, sparse=True),
        db.admin_accounts.create_index("username", unique=True),
        db.admin_login_attempts.create_index("identifier"),
        db.admin_login_attempts.create_index("ts"),
        db.admin_login_attempts.create_index(
            [("identifier", 1), ("success", 1), ("ts", -1)]
        ),
        db.giveaway_entries.create_index(
            [("giveaway_id", 1), ("user_id", 1)], unique=True
        ),
        db.game_entries.create_index(
            [("game_id", 1), ("user_id", 1)], unique=True
        ),
        db.game_entries.create_index([("game_id", 1), ("choice", 1)]),
        db.rewards.create_index([("active", 1), ("cost", 1)]),
        db.games.create_index([("status", 1), ("created_at", -1)]),
        db.giveaways.create_index([("status", 1), ("created_at", -1)]),
        db.custom_leaderboard.create_index([("board", 1), ("wagered", -1)]),
    )

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
    if not existing_admin:
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await db.admin_accounts.insert_one(AdminAccount(
            username=ADMIN_USERNAME, password_hash=hashed,
        ).to_mongo())
        log.info("Seeded admin account: %s", ADMIN_USERNAME)
    elif not bcrypt.checkpw(ADMIN_PASSWORD.encode("utf-8"), existing_admin["password_hash"].encode("utf-8")):
        hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
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
    await _close_http_client()
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
    try:
        hc = await _get_http_client()
        tok = await hc.post(
            "https://discord.com/api/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code", "code": code, "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if tok.status_code != 200:
            log.error("Discord token exchange failed with status %s", tok.status_code)
            return oauth_error()
        access_token = tok.json()["access_token"]
        me = await hc.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return oauth_error()
        du = me.json()
        if not isinstance(du, dict) or not du.get("id"):
            log.warning("Discord user response did not contain an id")
            return oauth_error()
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("Discord OAuth upstream request failed: %s", exc)
        return oauth_error()

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
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@api.post("/admin/login")
async def admin_login(body: AdminLoginBody, request: Request, response: Response):
    identifiers = [
        f"ip:{_client_ip(request)}",
        f"user:{body.username.lower()}",
    ]
    for identifier in identifiers:
        await _check_bruteforce(identifier)

    doc = await db.admin_accounts.find_one({"username": body.username})
    valid_password = False
    if doc and isinstance(doc.get("password_hash"), str):
        try:
            valid_password = bcrypt.checkpw(
                body.password.encode("utf-8"),
                doc["password_hash"].encode("utf-8"),
            )
        except (ValueError, TypeError):
            log.warning("Admin account has an invalid password hash")
    if not valid_password:
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
        if not isinstance(row, dict):
            continue
        u = row.get("user") or {}
        name = u.get("name") or "Anon"
        try:
            wagered = round(float(row.get("wagerAmount") or 0), 2)
            bets = int(row.get("betCount") or 0)
        except (TypeError, ValueError):
            continue
        lockly_rows.append({
            "name": (name[:3] + "***") if mask and len(name) > 3 else name,
            "wagered": wagered,
            "bets": bets,
            "source": "lockly",
        })

    # merge with custom entries for the same board
    custom_docs = await db.custom_leaderboard.find(
        {"board": type},
        {"display_name": 1, "wagered": 1, "bets": 1},
    ).sort("wagered", -1).limit(500).to_list(500)
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
    upstream_total_users = ro.get("totalUsers")
    upstream_total_wagered = ro.get("totalWagered")
    try:
        total_users = int(upstream_total_users) + len(custom_docs)
    except (TypeError, ValueError):
        total_users = len(lockly_rows)
    try:
        total_wagered = round(
            float(upstream_total_wagered)
            + sum(float(d.get("wagered") or 0) for d in custom_docs),
            2,
        )
    except (TypeError, ValueError):
        total_wagered = round(sum(r["wagered"] for r in lockly_rows), 2)
    return {
        "type": ro.get("type", type),
        "from": ro.get("from"),
        "total_users": total_users,
        "total_wagered": total_wagered,
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
    limit = max(1, min(limit, 100))
    docs = await db.ledger.find(
        {"user_id": user.discord_id},
        {"delta": 1, "balance_after": 1, "reason": 1, "ref": 1, "created_at": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"entries": [{
        "delta": d["delta"], "balance_after": d["balance_after"],
        "reason": d["reason"], "ref": d.get("ref"), "created_at": d["created_at"],
    } for d in docs]}


@api.get("/points/redemptions")
async def points_redemptions(user: User = Depends(_current_user)):
    docs = await db.ledger.find({
        "user_id": user.discord_id, "reason": "store_redeem"
    }, {
        "delta": 1, "ref": 1, "created_at": 1,
    }).sort("created_at", -1).limit(100).to_list(100)
    from bson import ObjectId as _OID
    reward_ids = {
        _OID(d["ref"])
        for d in docs
        if d.get("ref") and _OID.is_valid(d["ref"])
    }
    reward_docs = await db.rewards.find(
        {"_id": {"$in": list(reward_ids)}},
        {"title": 1},
    ).to_list(len(reward_ids)) if reward_ids else []
    reward_titles = {str(d["_id"]): d["title"] for d in reward_docs}
    out = []
    for d in docs:
        out.append({
            "reward_title": reward_titles.get(str(d.get("ref")), "Reward"),
            "cost": -d["delta"],
            "created_at": d["created_at"],
        })
    return {"redemptions": out}


@api.get("/points/leaderboard")
async def points_leaderboard(limit: int = 20):
    limit = max(1, min(limit, 100))
    docs = await db.users.find(
        {"points_balance": {"$gt": 0}},
        {"username": 1, "avatar_url": 1, "points_balance": 1},
    ).sort("points_balance", -1).limit(limit).to_list(limit)
    return {"leaderboard": [{
        "rank": i + 1, "username": d["username"], "avatar_url": d.get("avatar_url"),
        "points": d["points_balance"],
    } for i, d in enumerate(docs)]}


# ---------- Store ----------
@api.get("/store/rewards")
async def list_rewards():
    docs = await db.rewards.find(
        {"active": True},
        {
            "title": 1, "description": 1, "cost": 1, "stock": 1,
            "image_url": 1, "category": 1, "requires": 1,
        },
    ).sort("cost", 1).limit(200).to_list(200)
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
            conflicting = await db.ledger.find_one(
                {"idempotency_key": body.idempotency_key},
                {"user_id": 1, "reason": 1},
                session=session,
            )
            if conflicting and (
                conflicting.get("user_id") != user.discord_id
                or conflicting.get("reason") != "store_redeem"
            ):
                raise HTTPException(409, "Idempotency key already belongs to another operation")
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
    docs = await db.games.find(
        {},
        {
            "title": 1, "kind": 1, "status": 1, "entry_cost": 1,
            "reward_pool": 1, "prompt": 1, "options": 1,
            "winning_option": 1, "created_at": 1,
        },
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"games": [{
        "id": str(d["_id"]), "title": d["title"], "kind": d["kind"], "status": d["status"],
        "entry_cost": d.get("entry_cost", 0), "reward_pool": d.get("reward_pool", 0),
        "prompt": d.get("prompt"), "options": d.get("options", []),
        "winning_option": d.get("winning_option"),
    } for d in docs]}


class GameCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=40)
    prompt: Optional[str] = Field(default=None, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=20)
    entry_cost: int = Field(default=0, ge=0)
    reward_pool: int = Field(default=0, ge=0)


@api.post("/admin/games")
async def create_game(body: GameCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.kind not in {"prediction", "quiz", "raffle"}:
        raise HTTPException(400, "Game kind must be prediction, quiz, or raffle")
    options = [option.strip() for option in body.options]
    if any(not option or len(option) > 200 for option in options):
        raise HTTPException(400, "Game options must be non-empty and at most 200 characters")
    if len(set(options)) != len(options):
        raise HTTPException(400, "Game options must be unique")
    game = StreamGame(**{**body.model_dump(), "options": options})
    res = await db.games.insert_one(game.to_mongo())
    return {"id": str(res.inserted_id)}


class GameResolve(BaseModel):
    winning_option: Optional[str] = Field(default=None, max_length=200)


async def _pay_game_winner_batch(session, game_id: str, winner_entries: list[dict], per_winner: int) -> int:
    if per_winner <= 0 or not winner_entries:
        return 0
    user_ids = list(dict.fromkeys(entry["user_id"] for entry in winner_entries))
    user_docs = await db.users.find(
        {"discord_id": {"$in": user_ids}},
        {
            "_id": 1, "discord_id": 1, "username": 1, "email": 1,
            "avatar_url": 1, "role": 1, "points_balance": 1,
            "created_at": 1, "updated_at": 1,
        },
        session=session,
    ).to_list(len(user_ids))
    users = {
        user.discord_id: user
        for user in (User.from_mongo(doc) for doc in user_docs)
        if user
    }
    paid = 0
    for winner_entry in winner_entries:
        user = users.get(winner_entry["user_id"])
        if not user:
            continue
        await _apply_ledger_in_transaction(
            session,
            user,
            per_winner,
            "game_reward",
            ref=game_id,
            idempotency_key=f"gp_{game_id}_{winner_entry['user_id']}",
        )
        paid += 1
    return paid


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
        if game_doc["status"] != "open":
            raise HTTPException(400, "Game is closed")
        options = game_doc.get("options") or []
        if body.winning_option is not None and body.winning_option not in options:
            raise HTTPException(400, "Winning option is not valid for this game")
        winners_q = {"game_id": game_id}
        if body.winning_option is not None:
            winners_q["choice"] = body.winning_option
        winner_count = await db.game_entries.count_documents(winners_q, session=session)
        pool = int(game_doc.get("reward_pool") or 0)
        per_winner = (pool // winner_count) if winner_count else 0
        winner_cursor = db.game_entries.find(
            winners_q,
            {"user_id": 1},
            session=session,
        ).batch_size(500)
        winner_batch = []
        paid_winners = 0
        async for winner_entry in winner_cursor:
            winner_batch.append(winner_entry)
            if len(winner_batch) < 500:
                continue
            paid_winners += await _pay_game_winner_batch(
                session, game_id, winner_batch, per_winner
            )
            winner_batch = []
        if winner_batch:
            paid_winners += await _pay_game_winner_batch(
                session, game_id, winner_batch, per_winner
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
        return {"ok": True, "winners": winner_count, "paid_winners": paid_winners, "per_winner": per_winner}

    return await _run_transaction(resolve_transaction)


class GameJoin(BaseModel):
    game_id: str = Field(min_length=1, max_length=64)
    choice: Optional[str] = Field(default=None, max_length=200)


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
        options = game_doc.get("options") or []
        if options and body.choice not in options:
            raise HTTPException(400, "Choice must match one of the game options")
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
    docs = await db.giveaways.find(
        {},
        {
            "title": 1, "description": 1, "prize": 1, "image_url": 1,
            "max_winners": 1, "status": 1, "ends_at": 1, "winners": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(50).to_list(50)
    giveaway_ids = [str(d["_id"]) for d in docs]
    entry_counts = {}
    if giveaway_ids:
        count_rows = await db.giveaway_entries.aggregate([
            {"$match": {"giveaway_id": {"$in": giveaway_ids}}},
            {"$group": {"_id": "$giveaway_id", "count": {"$sum": 1}}},
        ]).to_list(len(giveaway_ids))
        entry_counts = {row["_id"]: row["count"] for row in count_rows}
    out = []
    for d in docs:
        giveaway_id = str(d["_id"])
        out.append({
            "id": giveaway_id, "title": d["title"], "description": d["description"],
            "prize": d["prize"], "image_url": d.get("image_url"),
            "max_winners": d.get("max_winners", 1),
            "status": d["status"], "ends_at": d.get("ends_at"),
            "winners": d.get("winners", []), "entries": entry_counts.get(giveaway_id, 0),
            "created_at": d["created_at"],
        })
    return {"giveaways": out}


class GiveawayEnterBody(BaseModel):
    giveaway_id: str = Field(min_length=1, max_length=64)


@api.post("/giveaways/enter")
async def enter_giveaway(body: GiveawayEnterBody, user: User = Depends(_current_user)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(body.giveaway_id)
    except Exception:
        raise HTTPException(400, "Invalid id")

    async def enter_transaction(session):
        giveaway = await db.giveaways.find_one(
            {"_id": oid, "status": "open"},
            {"_id": 1},
            session=session,
        )
        if not giveaway:
            exists = await db.giveaways.find_one({"_id": oid}, {"_id": 1}, session=session)
            if not exists:
                raise HTTPException(404, "Giveaway not found")
            raise HTTPException(400, "Giveaway closed")
        await db.giveaway_entries.insert_one(
            GiveawayEntry(
                giveaway_id=body.giveaway_id,
                user_id=user.discord_id,
                username=user.username,
            ).to_mongo(),
            session=session,
        )
        return await db.giveaway_entries.count_documents(
            {"giveaway_id": body.giveaway_id},
            session=session,
        )

    try:
        total = await _run_transaction(enter_transaction)
    except DuplicateKeyError:
        raise HTTPException(400, "Already entered")
    return {"ok": True, "entries": total}


class GiveawayCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    prize: str = Field(min_length=1, max_length=200)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    max_winners: int = Field(default=1, ge=1, le=100)


@api.post("/admin/giveaways")
async def admin_create_giveaway(body: GiveawayCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.image_url and not _is_http_url(body.image_url):
        raise HTTPException(400, "image_url must be an http(s) URL")
    g = Giveaway(**body.model_dump())
    res = await db.giveaways.insert_one(g.to_mongo())
    return {"id": str(res.inserted_id)}


async def _secure_sample_entries(cursor, sample_size: int) -> list[dict]:
    """Reservoir-sample entries with system randomness and bounded memory."""
    reservoir: list[dict] = []
    if sample_size <= 0:
        return reservoir
    seen = 0
    async for entry in cursor:
        seen += 1
        if len(reservoir) < sample_size:
            reservoir.append(entry)
            continue
        replacement = secrets.randbelow(seen)
        if replacement < sample_size:
            reservoir[replacement] = entry
    return reservoir


@api.post("/admin/giveaways/{gid}/draw")
async def admin_draw_giveaway(gid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(gid)
    except Exception:
        raise HTTPException(400, "Invalid giveaway id")

    async def draw_transaction(session):
        giveaway = await db.giveaways.find_one({"_id": oid}, session=session)
        if not giveaway:
            raise HTTPException(404, "Giveaway not found")
        if giveaway["status"] == "drawn":
            raise HTTPException(400, "Already drawn")
        if giveaway["status"] != "open":
            raise HTTPException(400, "Giveaway is closed")

        entry_count = await db.giveaway_entries.count_documents(
            {"giveaway_id": gid},
            session=session,
        )
        if not entry_count:
            raise HTTPException(400, "No entries")
        n = min(
            int(giveaway.get("max_winners") or 1),
            entry_count,
            MAX_GIVEAWAY_WINNERS,
        )
        winners_e = await _secure_sample_entries(
            db.giveaway_entries.find(
                {"giveaway_id": gid},
                {"user_id": 1, "username": 1},
                session=session,
            ).batch_size(500),
            n,
        )
        winners = [
            {"discord_id": winner["user_id"], "username": winner["username"]}
            for winner in winners_e
        ]
        updated = await db.giveaways.update_one(
            {"_id": oid, "status": "open"},
            {"$set": {
                "status": "drawn", "drawn_at": utcnow().isoformat(),
                "winners": winners,
            }},
            session=session,
        )
        if updated.matched_count != 1:
            raise HTTPException(400, "Giveaway was already drawn or closed")
        return winners

    winners = await _run_transaction(draw_transaction)
    return {"ok": True, "winners": winners}


@api.post("/admin/giveaways/{gid}/close")
async def admin_close_giveaway(gid: str, _: dict = Depends(_require_owner_or_admin)):
    from bson import ObjectId as _OID
    try:
        oid = _OID(gid)
    except Exception:
        raise HTTPException(400, "Invalid giveaway id")
    r = await db.giveaways.update_one(
        {"_id": oid, "status": "open"},
        {"$set": {"status": "closed"}},
    )
    if r.matched_count == 0:
        existing = await db.giveaways.find_one({"_id": oid}, {"status": 1})
        if not existing:
            raise HTTPException(404, "Not found")
        raise HTTPException(400, "Giveaway is already closed or drawn")
    return {"ok": True}


# ---------- Custom leaderboard entries (admin adds anyone manually) ----------
class CustomLBCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    wagered: float = Field(ge=0)
    bets: int = Field(default=0, ge=0)
    board: str = Field(default="monthly", min_length=1, max_length=20)
    note: Optional[str] = Field(default=None, max_length=500)


@api.get("/admin/custom-leaderboard")
async def admin_list_custom_lb(_: dict = Depends(_require_owner_or_admin)):
    docs = await db.custom_leaderboard.find(
        {},
        {"display_name": 1, "wagered": 1, "bets": 1, "board": 1, "note": 1},
    ).sort("wagered", -1).limit(500).to_list(500)
    return {"entries": [{
        "id": str(d["_id"]), "display_name": d["display_name"],
        "wagered": d["wagered"], "bets": d.get("bets", 0),
        "board": d.get("board", "monthly"), "note": d.get("note"),
    } for d in docs]}


@api.post("/admin/custom-leaderboard")
async def admin_add_custom_lb(body: CustomLBCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.board not in {"daily", "weekly", "monthly"}:
        raise HTTPException(400, "invalid board")
    if not math.isfinite(body.wagered):
        raise HTTPException(400, "wagered must be finite")
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
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    cost: int = Field(ge=0)
    stock: int = Field(default=-1, ge=-1)
    image_url: Optional[str] = Field(default=None, max_length=2000)
    category: str = Field(default="custom", min_length=1, max_length=40)
    requires: Optional[str] = Field(default=None, max_length=200)


@api.post("/admin/rewards")
async def admin_create_reward(body: RewardCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.image_url and not _is_http_url(body.image_url):
        raise HTTPException(400, "image_url must be an http(s) URL")
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
    discord_id: str = Field(min_length=1, max_length=100)
    delta: int
    reason: str = Field(default="admin_grant", min_length=1, max_length=100)
    idempotency_key: Optional[str] = Field(default=None, max_length=200)


@api.post("/admin/points/grant")
async def admin_grant(body: GrantBody, _: dict = Depends(_require_owner_or_admin)):
    u = User.from_mongo(await db.users.find_one({"discord_id": body.discord_id}))
    if not u:
        raise HTTPException(404, "User not found")
    entry = await _apply_ledger(
        u,
        body.delta,
        body.reason,
        idempotency_key=body.idempotency_key,
    )
    return {"ok": True, "balance_after": entry.balance_after}


@api.get("/admin/users")
async def admin_users(_: dict = Depends(_require_owner_or_admin)):
    docs = await db.users.find(
        {},
        {
            "discord_id": 1, "username": 1, "email": 1,
            "role": 1, "points_balance": 1,
        },
    ).sort("created_at", -1).limit(1000).to_list(1000)
    return {"users": [{
        "discord_id": d["discord_id"], "username": d["username"], "email": d.get("email"),
        "role": d["role"], "points_balance": d["points_balance"],
    } for d in docs]}


# ---------- Live status (LIVE ON KICK widget) ----------
@api.get("/live")
async def get_live():
    doc = await db.live_status.find_one(
        {},
        {"is_live": 1, "platform": 1, "title": 1, "url": 1},
    )
    if not doc:
        return {"is_live": False, "platform": "kick", "url": "https://kick.com/greekgodberry"}
    platform = doc.get("platform", "kick")
    url = doc.get("url")
    return {
        "is_live": bool(doc.get("is_live", False)),
        "platform": platform if platform in {"kick", "twitch", "youtube"} else "kick",
        "title": doc.get("title"),
        "url": url if _is_http_url(url) else "https://kick.com/greekgodberry",
    }


class LiveUpdate(BaseModel):
    is_live: bool
    title: Optional[str] = Field(default=None, max_length=200)
    platform: str = Field(default="kick", min_length=1, max_length=20)
    url: Optional[str] = Field(default=None, max_length=2000)


@api.post("/admin/live")
async def admin_set_live(body: LiveUpdate, _: dict = Depends(_require_owner_or_admin)):
    if body.platform not in {"kick", "twitch", "youtube"}:
        raise HTTPException(400, "platform must be kick, twitch, or youtube")
    if body.url and not _is_http_url(body.url):
        raise HTTPException(400, "url must be an http(s) URL")
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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-Requested-With"],
)
