"""GreekGodBerry Community Platform — FastAPI backend."""
from __future__ import annotations

import os
import time
import logging
import secrets
import hashlib
import hmac
import asyncio
import math
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlencode, urlparse

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


def _is_private_host(value: str) -> bool:
    """Reject hosts that resolve to private/link-local ranges (SSRF guard)."""
    from urllib.parse import urlsplit
    import socket as _socket

    host = urlsplit(value).hostname
    if not host:
        return True
    lowered = host.lower()
    if lowered == "localhost" or lowered.endswith(".localhost"):
        return True
    try:
        infos = _socket.getaddrinfo(host, None, type=_socket.SOCK_STREAM)
    except _socket.gaierror:
        return True  # unresolvable host — treat as unsafe
    for info in infos:
        addr = info[4][0]
        if addr.startswith(("10.", "192.168.", "127.", "169.254.")):
            return True
        try:
            import ipaddress
            ip = ipaddress.ip_address(addr)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return True
        except ValueError:
            return True
    return False


def _is_safe_bridge_url(value: Optional[str]) -> bool:
    """Bridge outbound URLs must be https and must not point at private hosts."""
    return bool(value) and _is_https_url(value) and not _is_private_host(value)


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

# --- Supabase Auth (single Discord login) -------------------------------------
# Optional. When both are set, the API ALSO accepts Supabase Auth access tokens
# (issued by the SPA's single Discord login) in _current_user and
# _require_owner_or_admin, alongside the legacy session JWTs. Legacy Discord
# OAuth keeps working so the cutover is gradual.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_AUTH_ENABLED = bool(SUPABASE_URL and SUPABASE_ANON_KEY)

# --- Phase 4: data-store toggle ----------------------------------------------
# mongo (default)  = legacy behavior, everything reads/writes Atlas
# postgres         = converted routes read/write Supabase Postgres via pg_store
# The toggle is per-route: routes not yet converted always use Mongo.
import pg_store

def _use_pg() -> bool:
    return pg_store.data_store() == "postgres" and pg_store.pg_enabled()

LOCKLY_STREAMER_BASE = "https://public-api.lockly.io/api/public/streamer"
KICK_CHANNEL = "greekgodberry"
KICK_API_BASE = "https://kick.com/api/v2"
CERBERUS_LIVE_STATE_URL = "".join(os.getenv("CERBERUS_LIVE_STATE_URL", "").split()).rstrip("/")
CERBERUS_API_KEY = os.getenv("CERBERUS_API_KEY", "").strip()
REFERENCE_BINGO_API_BASE = "".join(os.getenv("REFERENCE_BINGO_API_BASE", "").split()).rstrip("/")
REFERENCE_BINGO_SLUG = os.getenv("REFERENCE_BINGO_SLUG", "bonus-bingo").strip()
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
AUTH_HANDOFF_TTL_SECONDS = 300

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
    "/api/kick/latest": "public, max-age=60, stale-while-revalidate=120",
    "/api/leaderboard": "public, max-age=60, stale-while-revalidate=120",
    "/api/cerberus/live-state": "public, max-age=5, stale-while-revalidate=10",
    "/api/bingo/active": "public, max-age=3, stale-while-revalidate=5",
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

# ================= Kick playback cache =================
_kick_latest_cache: tuple[float, dict] | None = None
_kick_latest_lock = asyncio.Lock()
KICK_CACHE_TTL = 60
_cerberus_live_cache: tuple[float, dict] | None = None
_cerberus_live_lock = asyncio.Lock()
CERBERUS_CACHE_TTL = 10
_bingo_active_cache: tuple[float, dict] | None = None
_bingo_active_lock = asyncio.Lock()
BINGO_CACHE_TTL = 3


def _stale_upstream_result(cache: tuple[float, dict] | None, error: str) -> dict:
    if not cache:
        return {"available": False, "stale": False, "error": error, "updated_at": None}
    timestamp, payload = cache
    return {
        **payload,
        "available": bool(payload.get("available")),
        "stale": True,
        "error": error,
        "updated_at": payload.get("updated_at") or timestamp,
    }


async def _fetch_cerberus_live_state() -> dict:
    global _cerberus_live_cache
    async with _cerberus_live_lock:
        now = time.time()
        if _cerberus_live_cache and now - _cerberus_live_cache[0] < CERBERUS_CACHE_TTL:
            return _cerberus_live_cache[1]
        if not CERBERUS_LIVE_STATE_URL or not CERBERUS_API_KEY:
            return _stale_upstream_result(None, "not_configured")
        try:
            hc = await _get_http_client()
            response = await hc.get(
                CERBERUS_LIVE_STATE_URL,
                headers={"x-cerberus-api-key": CERBERUS_API_KEY},
            )
            if response.status_code != 200:
                raise ValueError(f"cerberus_status_{response.status_code}")
            payload = response.json()
            if (
                not isinstance(payload, dict)
                or payload.get("ok") is not True
                or not isinstance(payload.get("games"), list)
            ):
                raise ValueError("cerberus_payload_invalid")
            safe = {
                "available": True,
                "stale": False,
                "error": None,
                "updated_at": payload.get("updatedAt"),
                "games": payload["games"],
            }
            _cerberus_live_cache = (now, safe)
            return safe
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            log.warning("Cerberus live-state request failed: %s", exc)
            return _stale_upstream_result(_cerberus_live_cache, str(exc))


def _sanitize_bingo_game(game: object) -> Optional[dict]:
    if game is None:
        return None
    if not isinstance(game, dict):
        raise ValueError("bingo_game_invalid")
    cells = game.get("cells")
    participants = game.get("participants")
    line_wins = game.get("lineWins")
    if not isinstance(cells, list) or not isinstance(participants, list) or not isinstance(line_wins, list):
        raise ValueError("bingo_payload_invalid")
    return {
        "id": game.get("id"),
        "streamGameId": game.get("streamGameId"),
        "title": game.get("title"),
        "keyword": game.get("keyword"),
        "gridSize": game.get("gridSize"),
        "linePoints": game.get("linePoints"),
        "status": game.get("status"),
        "currentCellId": game.get("currentCellId"),
        "currentChatUsername": game.get("currentChatUsername"),
        "createdAt": game.get("createdAt"),
        "updatedAt": game.get("updatedAt"),
        "completedAt": game.get("completedAt"),
        "cells": [
            {
                "id": cell.get("id"),
                "row": cell.get("row"),
                "col": cell.get("col"),
                "status": cell.get("status"),
                "slotName": cell.get("slotName"),
                "claimedByChatUsername": cell.get("claimedByChatUsername"),
                "claimedAt": cell.get("claimedAt"),
            }
            for cell in cells
            if isinstance(cell, dict)
        ],
        "participants": [
            {
                "id": participant.get("id"),
                "chatUsername": participant.get("chatUsername"),
                "preferredSlot": participant.get("preferredSlot"),
                "joinedAt": participant.get("joinedAt"),
            }
            for participant in participants
            if isinstance(participant, dict)
        ],
        "lineWins": [
            {
                "id": line.get("id"),
                "lineType": line.get("lineType"),
                "lineIndex": line.get("lineIndex"),
                "pointsEach": line.get("pointsEach"),
                "winners": line.get("winners"),
                "completedAt": line.get("completedAt"),
            }
            for line in line_wins
            if isinstance(line, dict)
        ],
    }


async def _fetch_reference_bingo() -> dict:
    global _bingo_active_cache
    async with _bingo_active_lock:
        now = time.time()
        if _bingo_active_cache and now - _bingo_active_cache[0] < BINGO_CACHE_TTL:
            return _bingo_active_cache[1]
        if not REFERENCE_BINGO_API_BASE or not REFERENCE_BINGO_SLUG:
            return _stale_upstream_result(None, "not_configured")
        url = (
            f"{REFERENCE_BINGO_API_BASE}/api/bingo/games/"
            f"{quote(REFERENCE_BINGO_SLUG, safe='')}/active"
        )
        try:
            hc = await _get_http_client()
            response = await hc.get(url)
            if response.status_code != 200:
                raise ValueError(f"reference_bingo_status_{response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("success") is not True:
                raise ValueError("reference_bingo_payload_invalid")
            safe = {
                "available": True,
                "stale": False,
                "error": None,
                "updated_at": now,
                "game": _sanitize_bingo_game(payload.get("game")),
            }
            _bingo_active_cache = (now, safe)
            return safe
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            log.warning("Reference Bingo request failed: %s", exc)
            return _stale_upstream_result(_bingo_active_cache, str(exc))


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
    if isinstance(cached, dict):
        return {
            **cached,
            "upstream_unavailable": True,
            "upstream_last_updated_at": cached.get("upstream_last_updated_at"),
        }
    return {
        "responseObject": {"type": kind, "rankings": [], "from": None},
        "upstream_unavailable": True,
        "upstream_last_updated_at": None,
    }


def _lockly_monthly_window(now: Optional[date] = None) -> tuple[str, str]:
    current = now or utcnow().date()
    month_index = current.year * 12 + current.month - 1
    offset = 0 if current.day >= 16 else -1
    start_index = month_index + offset
    end_index = start_index + 1
    start = date(start_index // 12, start_index % 12 + 1, 16)
    end = date(end_index // 12, end_index % 12 + 1, 16)
    return start.isoformat(), end.isoformat()


async def _fetch_lockly(kind: str) -> dict:
    lock = await _lockly_lock(kind)
    async with lock:
        now = time.time()
        if kind == "monthly":
            range_from, range_to = _lockly_monthly_window()
            cache_key = f"{kind}:{range_from}:{range_to}"
            endpoint = f"{LOCKLY_API_BASE}/leaderboard/date-range"
            params = {"from": range_from, "to": range_to, "limit": LOCKLY_LIMIT}
        else:
            cache_key = kind
            endpoint = f"{LOCKLY_API_BASE}/leaderboard"
            params = {"type": kind, "limit": LOCKLY_LIMIT}
        cached_entry = _lockly_cache.get(cache_key)
        if cached_entry and now - cached_entry[0] < LOCKLY_TTL:
            return cached_entry[1]

        cached = cached_entry[1] if cached_entry else None
        if _lockly_retry_at.get(cache_key, 0) > now:
            return _lockly_unavailable(kind, cached)
        try:
            hc = await _get_http_client()
            response = await hc.get(
                endpoint,
                params=params,
                headers={"x-streamer-api-key": LOCKLY_API_KEY},
            )
            if response.status_code != 200:
                retry_after = response.headers.get("retry-after")
                retry_seconds = _retry_after_seconds(retry_after)
                if retry_seconds is None:
                    retry_seconds = 300 if response.status_code == 401 else 30
                _lockly_retry_at[cache_key] = now + retry_seconds
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
            _lockly_retry_at[cache_key] = now + 30
            return _lockly_unavailable(kind, cached)

        _lockly_retry_at.pop(cache_key, None)
        data = {
            **data,
            "upstream_last_updated_at": time.time(),
            "upstream_unavailable": False,
        }
        _lockly_cache[cache_key] = (time.time(), data)
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


async def _resolve_supabase_user(token: str) -> Optional[User]:
    """Validate a Supabase Auth access token and map it to a local user.

    Returns None when the token isn't a valid Supabase session, so the caller can
    fall back to legacy JWT handling. The Discord identity comes from the token's
    identities; admin/owner role is re-derived server-side from the allowlist
    semantics already stored on the Mongo user (role is never client-asserted).
    """
    if not SUPABASE_AUTH_ENABLED:
        return None
    # Cheap structural check: Supabase access tokens are JWTs whose issuer is the
    # project's auth server. Legacy session JWTs have no iss claim. This avoids a
    # wasted network call for every legacy-token request.
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    issuer = str(claims.get("iss") or "")
    if f"{SUPABASE_URL}/auth/v1" not in issuer:
        return None
    hc = await _get_http_client()
    try:
        resp = await hc.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=8.0,
        )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except ValueError:
        return None

    identity = (payload.get("identities") or [{}])[0]
    id_data = identity.get("identity_data") or {}
    meta = payload.get("user_metadata") or {}
    discord_id = str(
        meta.get("discord_id")
        or id_data.get("discord_id")
        or id_data.get("sub")
        or identity.get("id")
        or payload.get("id")
        or ""
    )
    if not discord_id:
        return None

    # Server-side admin allowlist check. This is the single source of truth for
    # the 3 admins; the result is mirrored into the Mongo role field that the
    # rest of the API reads. Never trusted from a client claim.
    is_admin = False
    try:
        check = await hc.get(
            f"{SUPABASE_URL}/rest/v1/app_admins",
            params={"discord_id": f"eq.{discord_id}", "select": "discord_id"},
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=8.0,
        )
        is_admin = check.status_code == 200 and bool(check.json())
    except httpx.HTTPError:
        pass  # non-fatal; role resolution falls back to stored Mongo role

    # Map to the existing Mongo user (created by the legacy OAuth flow or the
    # signup-bonus transaction). Role comes from Mongo, never from the token.
    doc = await db.users.find_one(
        {"discord_id": discord_id},
        {
            "_id": 1, "discord_id": 1, "username": 1, "email": 1,
            "avatar_url": 1, "role": 1, "points_balance": 1,
            "created_at": 1, "updated_at": 1,
        },
    )
    if not doc:
        # First Supabase login for a user that never went through legacy OAuth:
        # create the row so points/ledger keep working. Signup bonus applies the
        # same as the legacy path.
        username = str(meta.get("full_name") or meta.get("name") or meta.get("user_name") or "Anon")
        avatar_url = meta.get("avatar_url") or None
        user = User(
            discord_id=discord_id, username=username, email=payload.get("email"),
            avatar_url=avatar_url,
            role="admin" if is_admin else "viewer",
            points_balance=0,
        )
        try:
            async def create_user_with_bonus(session):
                await db.users.insert_one(user.to_mongo(), session=session)
                await _apply_ledger_in_transaction(
                    session, user, 100, "signup_bonus",
                    idempotency_key=f"signup_{discord_id}",
                )
            await _run_transaction(create_user_with_bonus)
        except DuplicateKeyError:
            log.info("Supabase user already existed concurrently: %s", discord_id)
        doc = await db.users.find_one(
            {"discord_id": discord_id},
            {
                "_id": 1, "discord_id": 1, "username": 1, "email": 1,
                "avatar_url": 1, "role": 1, "points_balance": 1,
                "created_at": 1, "updated_at": 1,
            },
        )
        if not doc:
            return None
    elif is_admin:
        current_role = (doc.get("role") or "viewer").lower()
        if current_role not in ("owner", "admin"):
            await db.users.update_one(
                {"discord_id": discord_id},
                {"$set": {"role": "admin", "updated_at": utcnow().isoformat()}},
            )
            doc["role"] = "admin"
    return User.from_mongo(doc)


async def _current_user(
    request: Request,
    ggb_session: Optional[str] = Cookie(default=None),
) -> User:
    token = ggb_session
    authorization = request.headers.get("authorization", "")
    if not token and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "Not authenticated")

    # Supabase (single Discord login) first — it is the going-forward identity.
    supabase_user = await _resolve_supabase_user(token)
    if supabase_user:
        return supabase_user

    sub = _decode_jwt(token, JWT_SECRET)
    if not sub:
        raise HTTPException(401, "Invalid session")
    # Logout revokes the exact token server-side; a revoked JWT (cookie or
    # Bearer) must never authenticate, otherwise logout appears not to work.
    if await db.revoked_tokens.find_one({"token_hash": _token_hash(token)}):
        raise HTTPException(401, "Session revoked — log in again")
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
    request: Request,
    ggb_session: Optional[str] = Cookie(default=None),
    ggb_admin: Optional[str] = Cookie(default=None),
) -> dict:
    """Either the Discord-owner OR the custom-admin can access."""
    if ggb_admin:
        sub = _decode_jwt(ggb_admin, ADMIN_JWT_SECRET)
        if sub == ADMIN_USERNAME:
            return {"kind": "admin", "username": sub}
    user_token = ggb_session
    authorization = request.headers.get("authorization", "")
    if not user_token and authorization.lower().startswith("bearer "):
        user_token = authorization[7:].strip()
    if user_token:
        # Supabase identity first (single Discord login going forward).
        supabase_user = await _resolve_supabase_user(user_token)
        if supabase_user:
            role = (supabase_user.role or "").lower()
            if role in ("owner", "admin"):
                return {"kind": "owner", "user": supabase_user}
            raise HTTPException(403, "Owner or admin required")

        sub = _decode_jwt(user_token, JWT_SECRET)
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
        ts=int(time.time()),
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
        db.oauth_states.create_index("state_hash", unique=True),
        db.oauth_states.create_index("expires_at", expireAfterSeconds=0),
        db.auth_handoffs.create_index("expires_at", expireAfterSeconds=0),
        db.revoked_tokens.create_index("expires_at", expireAfterSeconds=0),
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
            Reward(
                title="$5 Lockly Tip",
                description="Redeem a $5 tip. Eligibility is verified through Lockly under code GREEK33.",
                cost=750,
                stock=-1,
                category="bonus",
                requires="Lockly username",
            ),
            Reward(
                title="$50 Bonus Buy - Keep 10% of payout",
                description="Redeem a $50 bonus buy. Eligibility is verified through Lockly under code GREEK33.",
                cost=1750,
                stock=-1,
                category="custom",
                requires="Lockly username",
            ),
            Reward(
                title="$20 Lockly Tip",
                description="Redeem a $20 tip after meeting the campaign wager requirement under code GREEK33.",
                cost=2500,
                stock=-1,
                category="custom",
                requires="Lockly username",
            ),
        ]
        for r in seeds:
            await db.rewards.insert_one(r.to_mongo())

    # Migrate older seeded rewards so the public shop has no Rainbet affiliation.
    await db.rewards.update_one(
        {"title": "$5 Rainbet Tip"},
        {"$set": {
            "title": "$5 Lockly Tip",
            "description": "Redeem a $5 tip. Eligibility is verified through Lockly under code GREEK33.",
            "category": "bonus",
            "requires": "Lockly username",
        }},
    )
    await db.rewards.update_one(
        {"title": "$100 BONUS BUY - Keep 10% of payout"},
        {"$set": {
            "title": "$50 Bonus Buy - Keep 10% of payout",
            "description": "Redeem a $50 bonus buy. Eligibility is verified through Lockly under code GREEK33.",
            "requires": "Lockly username",
        }},
    )
    await db.rewards.update_one(
        {"title": "$20 Rainbet Tip"},
        {"$set": {
            "title": "$20 Lockly Tip",
            "description": "Redeem a $20 tip after meeting the campaign wager requirement under code GREEK33.",
            "requires": "Lockly username",
        }},
    )
    await db.rewards.update_many(
        {"title": {"$in": [
            "$200 BONUS BUY - Keep 10% of payout",
            "BEST OF 3 - $100 BONUS BUY - Keep 10% of payout",
            "$1,000 50/50 Split Bonus Hunt with Cam!",
        ]}},
        {"$set": {"active": False}},
    )

    # Seed public streamer game templates. They are free to enter and remain
    # admin-manageable through the existing resolve/close controls.
    stream_game_seeds = [
        StreamGame(
            title="Bonus Hunt",
            kind="raffle",
            prompt="Join the next bonus hunt and follow the live call.",
            options=["Join"],
            entry_cost=0,
            reward_pool=0,
        ),
        StreamGame(
            title="Tournament",
            kind="prediction",
            prompt="Enter the next community tournament.",
            options=["Join"],
            entry_cost=0,
            reward_pool=0,
        ),
        StreamGame(
            title="Chat vs Streamer",
            kind="prediction",
            prompt="Who wins the next round?",
            options=["Chat", "Streamer"],
            entry_cost=0,
            reward_pool=0,
        ),
        StreamGame(
            title="Climb the Ladder",
            kind="quiz",
            prompt="Predict whether the next climb passes or fails.",
            options=["Pass", "Fail"],
            entry_cost=0,
            reward_pool=0,
        ),
        StreamGame(
            title="Bonus Bingo",
            kind="raffle",
            prompt="Join the next bonus bingo draw.",
            options=["Join"],
            entry_cost=0,
            reward_pool=0,
        ),
    ]
    for game_seed in stream_game_seeds:
        if not await db.games.find_one({"title": game_seed.title}, {"_id": 1}):
            await db.games.insert_one(game_seed.to_mongo())

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
    await pg_store.close_pg()
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


# ---------- Discord token-exchange proxy (for greek-bingo's Cloudflare-blocked egress) ----------
DISCORD_PROXY_SHARED_SECRET = os.getenv("DISCORD_PROXY_SHARED_SECRET", "").strip()
DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"


@api.post("/proxy/discord-token")
async def proxy_discord_token(request: Request):
    """Forward a Discord OAuth token-exchange request from greek-bingo (whose egress IP is
    Cloudflare 1015-rate-limited by Discord) through this backend's egress IP.

    Only accepts requests carrying the shared secret; only forwards to Discord's exact
    token endpoint. Never returns the shared secret.
    """
    if not DISCORD_PROXY_SHARED_SECRET:
        raise HTTPException(503, "proxy_not_configured")
    provided = request.headers.get("x-proxy-secret", "")
    if provided != DISCORD_PROXY_SHARED_SECRET:
        raise HTTPException(403, "forbidden")
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        try:
            body = await request.body()
        except Exception:
            raise HTTPException(400, "bad_body")
    else:
        raise HTTPException(400, "invalid_content_type")
    hc = await _get_http_client()
    try:
        resp = await hc.post(DISCORD_TOKEN_URL, content=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except httpx.HTTPError as exc:
        log.warning("Discord token proxy request failed: %s", exc)
        raise HTTPException(502, "upstream_failed")
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


# ---------- Discord OAuth ----------
def _oauth_failure_reason(
    *,
    error: Optional[str] = None,
    state: Optional[str] = None,
    token_status: Optional[int] = None,
    profile_status: Optional[int] = None,
) -> str:
    if error:
        return "oauth_denied"
    if state:
        return "state_invalid"
    if token_status is not None and token_status != 200:
        return "token_exchange"
    if profile_status is not None and profile_status != 200:
        return "discord_profile"
    return "oauth_failed"


def _oauth_error_response(reason: str) -> RedirectResponse:
    response = RedirectResponse(
        f"{FRONTEND_URL}/?{urlencode({'auth': 'error', 'reason': reason})}"
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/discord")
    return response


def _handoff_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def _token_hash(token: str) -> str:
    """Hash a session JWT so revocations never store the raw token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _revoke_token(token: str) -> None:
    """Add a session JWT to the revocation list until its natural expiry."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        exp = payload.get("exp")
        ttl = max(60, int(exp - utcnow().timestamp())) if exp else 7 * 86400
    except jwt.PyJWTError:
        ttl = 7 * 86400
    await db.revoked_tokens.update_one(
        {"token_hash": _token_hash(token)},
        {"$set": {"expires_at": utcnow() + timedelta(seconds=ttl)}},
        upsert=True,
    )


def _oauth_state_hash(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def _create_auth_handoff(discord_id: str) -> str:
    ticket = secrets.token_urlsafe(32)
    now = utcnow()
    await db.auth_handoffs.insert_one({
        "token_hash": _handoff_hash(ticket),
        "discord_id": discord_id,
        "created_at": now,
        "expires_at": now + timedelta(seconds=AUTH_HANDOFF_TTL_SECONDS),
    })
    return ticket


@api.get("/auth/discord/login")
async def discord_login(response: Response):
    state = secrets.token_urlsafe(16)
    now = utcnow()
    await db.oauth_states.insert_one({
        "state_hash": _oauth_state_hash(state),
        "created_at": now,
        "expires_at": now + timedelta(seconds=600),
    })
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
    return {"url": url}


@api.get("/auth/discord/callback")
async def discord_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    if error:
        return _oauth_error_response(_oauth_failure_reason(error=error))
    if not code:
        return _oauth_error_response(_oauth_failure_reason())
    if not state:
        log.warning("Rejected Discord OAuth callback with invalid state")
        return _oauth_error_response(_oauth_failure_reason(state="invalid"))
    oauth_state = await db.oauth_states.find_one_and_delete({
        "state_hash": _oauth_state_hash(state),
        "expires_at": {"$gt": utcnow()},
    })
    if not oauth_state:
        log.warning("Rejected Discord OAuth callback with expired or unknown state")
        return _oauth_error_response(_oauth_failure_reason(state="invalid"))
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
            return _oauth_error_response(
                _oauth_failure_reason(token_status=tok.status_code)
            )
        access_token = tok.json()["access_token"]
        me = await hc.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if me.status_code != 200:
            return _oauth_error_response(
                _oauth_failure_reason(profile_status=me.status_code)
            )
        du = me.json()
        if not isinstance(du, dict) or not du.get("id"):
            log.warning("Discord user response did not contain an id")
            return _oauth_error_response(
                _oauth_failure_reason(profile_status=200)
            )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("Discord OAuth upstream request failed: %s", exc)
        return _oauth_error_response(_oauth_failure_reason())

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
    handoff = await _create_auth_handoff(discord_id)
    resp = RedirectResponse(
        f"{FRONTEND_URL}/?{urlencode({'auth': 'success', 'auth_ticket': handoff})}"
    )
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=JWT_TTL_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/")
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/discord")
    return resp


class AuthHandoffBody(BaseModel):
    ticket: str = Field(min_length=20, max_length=200)


@api.post("/auth/discord/complete")
async def complete_discord_auth(body: AuthHandoffBody, response: Response):
    doc = await db.auth_handoffs.find_one_and_delete({
        "token_hash": _handoff_hash(body.ticket),
        "expires_at": {"$gt": utcnow()},
    })
    if not doc:
        raise HTTPException(401, "Login handoff expired or already used. Try Discord login again.")
    token = _make_jwt(doc["discord_id"], JWT_SECRET, JWT_TTL_DAYS * 86400)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=JWT_TTL_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/",
    )
    return {"ok": True, "token": token}


@api.get("/auth/me")
async def auth_me(user: User = Depends(_current_user)):
    return _public(user)


@api.post("/auth/logout")
async def auth_logout(request: Request, response: Response):
    # Revoke the exact session JWT (cookie or Bearer) server-side. Without
    # this the stateless JWT stays valid for its full TTL and the frontend
    # restores the session from it — logout looked like it did nothing.
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
    if token:
        await _revoke_token(token)
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
HIDDEN_LEADERBOARD_NAMES = frozenset({"tricketo", "tricket0"})


def _is_hidden_leaderboard_name(name: object) -> bool:
    return isinstance(name, str) and name.strip().casefold() in HIDDEN_LEADERBOARD_NAMES


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
        name = u.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if _is_hidden_leaderboard_name(name):
            continue
        try:
            wagered = round(float(row.get("wagerAmount") or 0), 2)
            bets = int(row.get("betCount") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(wagered) or wagered < 0 or bets < 0:
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
    custom_entries = []
    for d in custom_docs:
        name = d.get("display_name")
        if _is_hidden_leaderboard_name(name):
            continue
        try:
            wagered = round(float(d.get("wagered") or 0), 2)
            bets = int(d.get("bets") or 0)
        except (TypeError, ValueError, OverflowError):
            continue
        if (
            not isinstance(name, str)
            or not name.strip()
            or not math.isfinite(wagered)
            or wagered < 0
            or bets < 0
        ):
            continue
        masked_name = (name[:3] + "***") if mask and len(name) > 3 else name
        custom_entries.append({
            "name": masked_name,
            "wagered": wagered,
            "bets": bets,
            "source": "custom",
        })
    lockly_rows.extend(custom_entries)

    lockly_rows.sort(key=lambda r: r["wagered"], reverse=True)
    for i, r in enumerate(lockly_rows):
        r["rank"] = i + 1
    upstream_total_users = ro.get("totalUsers")
    upstream_total_wagered = ro.get("totalWagered")
    upstream_unavailable = bool(data.get("upstream_unavailable"))
    # Hidden names (e.g. tricket0) are excluded from rows; subtract them from the
    # upstream totals too so the summary matches what viewers actually see.
    hidden_count = 0
    hidden_wagered = 0.0
    for row in ro.get("rankings") or []:
        if not isinstance(row, dict):
            continue
        hu = row.get("user") or {}
        if _is_hidden_leaderboard_name(hu.get("name")):
            hidden_count += 1
            try:
                hw = round(float(row.get("wagerAmount") or 0), 2)
                if math.isfinite(hw) and hw >= 0:
                    hidden_wagered += hw
            except (TypeError, ValueError, OverflowError):
                pass
    if upstream_unavailable:
        total_users = len(custom_entries)
        total_wagered = round(sum(d["wagered"] for d in custom_entries), 2)
        source_status = "unavailable" if not custom_entries else "custom_only"
    else:
        try:
            total_users = max(0, int(upstream_total_users) - hidden_count) + len(custom_entries)
        except (TypeError, ValueError):
            total_users = len(lockly_rows) + len(custom_entries)
        try:
            total_wagered = round(
                max(0.0, float(upstream_total_wagered) - hidden_wagered)
                + sum(d["wagered"] for d in custom_entries),
                2,
            )
        except (TypeError, ValueError):
            total_wagered = round(sum(r["wagered"] for r in lockly_rows) + sum(d["wagered"] for d in custom_entries), 2)
        source_status = "lockly" if lockly_rows else ("custom_only" if custom_entries else "lockly_empty")
    return {
        "type": ro.get("type", type),
        "from": ro.get("from"),
        "to": ro.get("to"),
        "total_users": total_users,
        "total_wagered": total_wagered,
        "rankings": lockly_rows,
        "cached_ttl_seconds": LOCKLY_TTL,
        "upstream_unavailable": upstream_unavailable,
        "source_status": source_status,
        "last_updated_at": data.get("upstream_last_updated_at"),
    }


# ---------- External live integrations ----------
@api.get("/cerberus/live-state")
async def cerberus_live_state():
    return await _fetch_cerberus_live_state()


@api.get("/bingo/active")
async def active_reference_bingo():
    return await _fetch_reference_bingo()


# ---------- Live stream-game states (bingo backend fan-out) ----------
# One endpoint the overlay polls for every bingo-backend game. Public data only;
# mirrors the admin console's own reads, minus anything moderator-gated.

_bingo_feeds_cache: dict = {}
_bingo_feeds_lock = asyncio.Lock()
BINGO_FEEDS_TTL = 5


@api.get("/stream-games/live")
async def stream_games_live():
    """Live state for all bingo-backend games in one response."""
    async with _bingo_feeds_lock:
        now = time.time()
        if _bingo_feeds_cache and now - _bingo_feeds_cache[0] < BINGO_FEEDS_TTL:
            return _bingo_feeds_cache[1]
        if not REFERENCE_BINGO_API_BASE:
            return {"available": False, "error": "not_configured", "games": {}}
        base = REFERENCE_BINGO_API_BASE.rstrip("/")
        hc = await _get_http_client()
        out: dict = {}
        ok_count = 0

        async def _get(path: str):
            try:
                r = await hc.get(f"{base}{path}", timeout=8.0)
                if r.status_code != 200:
                    return None
                payload = r.json()
                return payload if isinstance(payload, dict) else None
            except (httpx.HTTPError, ValueError):
                return None

        predictions = await _get("/api/predictions/games/chat-vs-streamer/active")
        if predictions and predictions.get("success"):
            m = predictions.get("match")
            if m:
                ok_count += 1
                out["chat_vs_streamer"] = {
                    "status": m.get("status"),
                    "format": m.get("format"),
                    "targetScore": m.get("targetScore"),
                    "chatScore": m.get("chatScore"),
                    "streamerScore": m.get("streamerScore"),
                    "chatStreak": m.get("chatStreak"),
                    "streamerStreak": m.get("streamerStreak"),
                    "winner": m.get("winner"),
                    "challengeText": m.get("challengeText"),
                    "createdAt": m.get("createdAt"),
                    "updatedAt": m.get("updatedAt"),
                    "currentRound": next(({
                        "roundNumber": r.get("roundNumber"),
                        "question": r.get("question"),
                        "streamerCall": r.get("streamerCall"),
                        "status": r.get("status"),
                        "votesChat": r.get("votesChat"),
                        "votesStreamer": r.get("votesStreamer"),
                        "chatPick": r.get("chatPick"),
                        "streamerCorrect": r.get("streamerCorrect"),
                        "lockedAt": r.get("lockedAt"),
                        "resolvedAt": r.get("resolvedAt"),
                    } for r in (m.get("rounds") or [])
                       if r.get("status") in ("OPEN", "LOCKED")), None),
                }

        ladder = await _get("/api/ladder/games/climb-the-ladder/active")
        if ladder and ladder.get("success"):
            run = ladder.get("run")
            if run:
                ok_count += 1
                out["climb_the_ladder"] = {
                    "status": run.get("status"),
                    "currentLevel": run.get("currentLevel"),
                    "finalPoints": run.get("finalPoints"),
                    "participantName": run.get("participantName"),
                    "attempts": run.get("attempts"),
                    "updatedAt": run.get("updatedAt"),
                }

        hunts = await _get("/api/hunts/live")
        if hunts and hunts.get("success"):
            hunt = hunts.get("hunt")
            if hunt:
                ok_count += 1
                out["bonus_hunt"] = {
                    "status": hunt.get("status"),
                    "title": hunt.get("title"),
                    "totalSlots": hunt.get("totalSlots"),
                    "completedSlots": hunt.get("completedSlots"),
                    "currentGame": hunt.get("currentGame"),
                    "multiplierSum": hunt.get("multiplierSum"),
                    "startBalance": hunt.get("startBalance"),
                    "updatedAt": hunt.get("updatedAt"),
                }

        tournaments = await _get("/api/tournaments")
        if tournaments and tournaments.get("success"):
            active = next((t for t in (tournaments.get("tournaments") or [])
                           if t.get("status") in ("ACTIVE", "REGISTRATION", "SLOT_SELECTION")), None)
            if active:
                ok_count += 1
                out["tournament"] = {
                    "status": active.get("status"),
                    "title": active.get("title"),
                    "maxPlayers": active.get("maxPlayers"),
                    "currentRound": active.get("currentRound"),
                    "prizeCoins": active.get("prizeCoins"),
                    "updatedAt": active.get("updatedAt"),
                }

        payload = {"available": True, "stale": False, "error": None, "games": out}
        _bingo_feeds_cache = (now, payload)
        return payload


# ---------- Points ----------
@api.get("/points/me")
async def points_me(user: User = Depends(_current_user)):
    return {"balance": user.points_balance, "discord_id": user.discord_id}


@api.get("/points/ledger")
async def points_ledger(user: User = Depends(_current_user), limit: int = 50):
    limit = max(1, min(limit, 100))
    if _use_pg():
        return {"entries": await pg_store.ledger_recent(user.discord_id, limit)}
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
    if _use_pg():
        return {"leaderboard": await pg_store.points_leaderboard(limit)}
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
    if _use_pg():
        return {"games": await pg_store.games_list()}
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
    entry_cost: int = Field(default=0, ge=0, le=1_000_000)
    reward_pool: int = Field(default=0, ge=0, le=1_000_000)


@api.post("/admin/games")
async def create_game(body: GameCreate, _: dict = Depends(_require_owner_or_admin)):
    if body.kind not in {"prediction", "quiz", "raffle"}:
        raise HTTPException(400, "Game kind must be prediction, quiz, or raffle")
    options = [option.strip() for option in body.options]
    if any(not option or len(option) > 200 for option in options):
        raise HTTPException(400, "Game options must be non-empty and at most 200 characters")
    if len(set(options)) != len(options):
        raise HTTPException(400, "Game options must be unique")
    if body.kind in {"prediction", "quiz"} and not options:
        raise HTTPException(400, "Prediction and quiz games require at least one option")
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
        kind = game_doc.get("kind")
        options = game_doc.get("options") or []
        if body.winning_option is None and kind == "prediction":
            raise HTTPException(400, "Prediction games require a winning option to resolve")
        if body.winning_option is not None and body.winning_option not in options:
            raise HTTPException(400, "Winning option is not valid for this game")
        winners_q = {"game_id": game_id}
        if body.winning_option is not None:
            winners_q["choice"] = body.winning_option
        winner_count = await db.game_entries.count_documents(winners_q, session=session)
        if winner_count == 0:
            raise HTTPException(400, "No winners for this option")
        pool = int(game_doc.get("reward_pool") or 0)
        per_winner = pool // winner_count
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
    fresh = await db.users.find_one({"discord_id": user.discord_id}, {"points_balance": 1})
    balance_after = fresh.get("points_balance", user.points_balance) if fresh else user.points_balance
    return {"ok": True, "balance_after": balance_after}


# ---------- GIVEAWAYS (public listing + entry, admin CRUD + draw) ----------
@api.get("/giveaways")
async def list_giveaways():
    if _use_pg():
        return {"giveaways": await pg_store.giveaways_list()}
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
    if _is_hidden_leaderboard_name(body.display_name):
        raise HTTPException(400, "display name is blocked")
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
    if body.delta == 0:
        raise HTTPException(400, "delta must be non-zero")
    entry = await _apply_ledger(
        u,
        body.delta,
        body.reason,
        idempotency_key=body.idempotency_key,
    )
    return {"ok": True, "balance_after": entry.balance_after}


@api.post("/admin/points/revoke")
async def admin_revoke(body: GrantBody, _: dict = Depends(_require_owner_or_admin)):
    """Reverse the most recent admin grant for a user atomically."""
    u = User.from_mongo(await db.users.find_one({"discord_id": body.discord_id}))
    if not u:
        raise HTTPException(404, "User not found")
    target = await db.ledger.find_one(
        {
            "user_id": body.discord_id,
            "reason": "admin_grant",
        },
        sort=[("created_at", -1), ("_id", -1)],
    )
    if not target:
        raise HTTPException(400, "No admin grant to revoke for this user")
    delta = int(target.get("delta") or 0)
    if delta == 0:
        raise HTTPException(400, "Last admin grant is a no-op")
    entry = await _apply_ledger(
        u,
        -delta,
        "admin_revoke",
        ref=target.get("idempotency_key") or str(target.get("_id")),
        idempotency_key=f"revoke_{target.get('idempotency_key') or target.get('_id')}",
    )
    return {"ok": True, "balance_after": entry.balance_after, "revoked": delta}


@api.get("/admin/users")
async def admin_users(_: dict = Depends(_require_owner_or_admin)):
    docs = await db.users.find(
        {},
        {
            "discord_id": 1, "username": 1, "email": 1,
            "role": 1, "points_balance": 1,
        },
    ).sort("created_at", -1).limit(1000).to_list(1000)
    user_ids = [d["discord_id"] for d in docs]
    last_grants = {}
    if user_ids:
        rows = await db.ledger.aggregate([
            {"$match": {"user_id": {"$in": user_ids}, "reason": "admin_grant"}},
            {"$sort": {"created_at": -1, "_id": -1}},
            {"$group": {"_id": "$user_id", "delta": {"$first": "$delta"}}},
        ]).to_list(len(user_ids))
        last_grants = {row["_id"]: row["delta"] for row in rows}
    return {"users": [{
        "discord_id": d["discord_id"], "username": d["username"], "email": d.get("email"),
        "role": d["role"], "points_balance": d["points_balance"],
        "last_grant": last_grants.get(d["discord_id"]),
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


async def _get_kick_playback() -> dict:
    global _kick_latest_cache
    now = time.monotonic()
    if _kick_latest_cache and now - _kick_latest_cache[0] < KICK_CACHE_TTL:
        return _kick_latest_cache[1]

    async with _kick_latest_lock:
        now = time.monotonic()
        if _kick_latest_cache and now - _kick_latest_cache[0] < KICK_CACHE_TTL:
            return _kick_latest_cache[1]

        try:
            http_client = await _get_http_client()
            headers = {
                "Accept": "application/json",
                "User-Agent": "GreekGodBerry-Website/1.0",
            }
            channel_response, videos_response = await asyncio.gather(
                http_client.get(f"{KICK_API_BASE}/channels/{KICK_CHANNEL}", headers=headers),
                http_client.get(f"{KICK_API_BASE}/channels/{KICK_CHANNEL}/videos", headers=headers),
            )
            channel_response.raise_for_status()
            videos_response.raise_for_status()
            channel = channel_response.json()
            videos = videos_response.json()
            latest = next(
                (
                    video for video in videos
                    if not video.get("is_live")
                    and _is_https_url(video.get("source"))
                    and video.get("video", {}).get("status") == "public"
                ),
                None,
            )
            vod = None
            if latest:
                vod_id = latest.get("video", {}).get("id") or latest.get("id")
                thumbnail = latest.get("thumbnail") or {}
                vod = {
                    "id": str(vod_id),
                    "title": latest.get("session_title") or "Latest Kick replay",
                    "source": latest["source"],
                    "thumbnail": thumbnail.get("src"),
                    "duration_ms": latest.get("duration"),
                    "url": f"https://kick.com/{KICK_CHANNEL}/videos/{vod_id}",
                }
            payload = {
                "channel": KICK_CHANNEL,
                "is_live": bool(channel.get("livestream")),
                "live_player_url": (
                    f"https://player.kick.com/{KICK_CHANNEL}"
                    "?autoplay=true&muted=true&playsinline=true"
                ),
                "latest_vod": vod,
                "stale": False,
            }
            _kick_latest_cache = (time.monotonic(), payload)
            return payload
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            log.warning("Kick playback metadata request failed: %s", exc)
            if _kick_latest_cache:
                return {**_kick_latest_cache[1], "stale": True}
            return {
                "channel": KICK_CHANNEL,
                "is_live": False,
                "live_player_url": f"https://player.kick.com/{KICK_CHANNEL}",
                "latest_vod": None,
                "stale": True,
            }


@api.get("/kick/latest")
async def get_kick_latest():
    return await _get_kick_playback()


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


# ---------- Internal points automation (chat awards + watch time) ----------
# Called by the greek-bingo backend (chat listeners) and the website client
# (watch heartbeat). Authenticated by a shared secret / user session; every
# award flows through _apply_ledger so the balance + audit trail stay intact.

INTERNAL_POINTS_SECRET = os.getenv("INTERNAL_POINTS_SECRET", "").strip()
CHAT_AWARD_COOLDOWN_SECONDS = 180
WATCH_BEAT_INTERVAL_SECONDS = 240  # 1 pt / 4 min == 15/hr
WATCH_POINTS_ENABLED = os.getenv("WATCH_POINTS_ENABLED", "true").strip().lower() == "true"
WATCH_POINTS_DAILY_CAP = int(os.getenv("WATCH_POINTS_DAILY_CAP", "360"))
CHAT_POINTS_ENABLED = os.getenv("CHAT_POINTS_ENABLED", "true").strip().lower() == "true"
_watch_live_cache: tuple = (0.0, False)  # (monotonic_ts, is_live)
_watch_live_lock = asyncio.Lock()


def _check_internal_secret(request: Request) -> None:
    provided = request.headers.get("x-internal-secret", "")
    if not INTERNAL_POINTS_SECRET or not provided:
        raise HTTPException(401, "Internal secret required")
    if not hmac.compare_digest(provided, INTERNAL_POINTS_SECRET):
        raise HTTPException(401, "Invalid internal secret")


async def _stream_is_live() -> bool:
    """Cached Kick live check (60s) — shared by every watch-beat request."""
    global _watch_live_cache
    now = time.monotonic()
    if now - _watch_live_cache[0] < 60:
        return _watch_live_cache[1]
    async with _watch_live_lock:
        now = time.monotonic()
        if now - _watch_live_cache[0] < 60:
            return _watch_live_cache[1]
        try:
            playback = await _get_kick_playback()
            is_live = bool(playback.get("is_live"))
        except Exception:
            # Fail closed: if we cannot confirm the stream is live, do not pay.
            is_live = False
        _watch_live_cache = (now, is_live)
        return is_live


class ChatAwardBody(BaseModel):
    discord_id: str = Field(min_length=5, max_length=25)
    source: str = Field(min_length=3, max_length=10)
    platform_username: str = Field(min_length=1, max_length=60)
    event_id: str = Field(min_length=8, max_length=80)


@api.post("/internal/points/chat-award")
async def internal_chat_award(request: Request, body: ChatAwardBody):
    _check_internal_secret(request)
    if not CHAT_POINTS_ENABLED:
        return {"awarded": False, "reason": "disabled"}
    if body.source not in {"kick", "twitch"}:
        raise HTTPException(422, "source must be kick or twitch")

    if _use_pg():
        return await pg_store.chat_award(
            body.discord_id, body.source, body.platform_username,
            body.event_id, CHAT_AWARD_COOLDOWN_SECONDS,
        )

    user_doc = await db.users.find_one({"discord_id": body.discord_id})
    if not user_doc:
        # No main-site account: skip silently (never auto-create; OAuth consent
        # is how accounts are born). The bingo-side CatCoin still applies.
        return {"awarded": False, "reason": "no_account"}
    user = User.from_mongo(user_doc)

    # Authoritative cooldown, checked inside the txn so concurrent callers
    # cannot double-pay. Per user + per source, 180s, matching the site copy.
    cutoff = time.time() - CHAT_AWARD_COOLDOWN_SECONDS
    recent = await db.ledger.find_one({
        "user_id": user.discord_id,
        "reason": f"chat_{body.source}",
        "ts": {"$gte": cutoff},
    })
    if recent:
        return {"awarded": False, "reason": "cooldown"}

    event_id = f"chat_{body.source}_{body.event_id}"
    try:
        entry = await _apply_ledger(
            user, 1, f"chat_{body.source}",
            ref=f"platform:{body.platform_username}",
            idempotency_key=event_id,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            # Same event_id replayed — idempotent success, nothing changed.
            return {"awarded": False, "reason": "duplicate"}
        raise
    return {"awarded": True, "balance": entry.balance_after}


class WatchBeatBody(BaseModel):
    pass


@api.post("/internal/points/watch-beat")
async def internal_watch_beat(request: Request, _: User = Depends(_current_user)):
    if not WATCH_POINTS_ENABLED:
        return {"awarded": False, "reason": "disabled"}

    if not await _stream_is_live():
        raise HTTPException(409, "Stream is not live")

    if _use_pg():
        bucket = int(time.time() // WATCH_BEAT_INTERVAL_SECONDS)
        return await pg_store.watch_beat(_, bucket, WATCH_POINTS_DAILY_CAP)

    # Daily cap: count today's watch ledger entries for this user.
    day_start = time.time() - (time.time() % 86400)
    today_count = await db.ledger.count_documents({
        "user_id": _.discord_id,
        "reason": "watch_time",
        "ts": {"$gte": day_start},
    })
    if today_count >= WATCH_POINTS_DAILY_CAP:
        return {"awarded": False, "reason": "daily_cap"}

    # Server-time bucket: 1 point per 240s window, replay-safe.
    bucket = int(time.time() // WATCH_BEAT_INTERVAL_SECONDS)
    event_id = f"watch_{_.discord_id}_{bucket}"
    try:
        entry = await _apply_ledger(
            _, 1, "watch_time",
            ref="stream_watch",
            idempotency_key=event_id,
        )
    except HTTPException as exc:
        if exc.status_code == 409:
            return {"awarded": False, "reason": "duplicate"}
        if exc.status_code == 400:
            return {"awarded": False, "reason": "balance_error"}
        raise
    return {"awarded": True, "balance": entry.balance_after}


# ---------- Mount ----------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Requested-With"],
)
