"""Postgres (Supabase) data layer — Phase 4.

Mirrors the Mongo queries used by server.py routes, keyed by discord_id exactly
like the Mongo layer, so routes stay readable and the DATA_STORE toggle can
switch per-request with no shape changes in responses.

Conventions:
  - All writes go through SECURITY DEFINER RPCs (atomic, idempotent).
  - Reads use PostgREST with service_role (bypasses RLS; the routes already
    enforce their own authz via _current_user / _require_owner_or_admin).
  - discord_id remains the user key (profiles.discord_id is indexed+unique).
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import httpx

from models import User, LedgerEntry

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
DATA_STORE = os.getenv("DATA_STORE", "mongo").strip().lower()  # mongo | postgres | dual

_pg_client: Optional[httpx.AsyncClient] = None


def pg_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def data_store() -> str:
    if DATA_STORE == "postgres" and not pg_enabled():
        return "mongo"
    return DATA_STORE if DATA_STORE in ("mongo", "postgres", "dual") else "mongo"


async def close_pg() -> None:
    global _pg_client
    if _pg_client is not None and not _pg_client.is_closed:
        await _pg_client.aclose()
    _pg_client = None


async def _client() -> httpx.AsyncClient:
    global _pg_client
    if _pg_client is None or _pg_client.is_closed:
        _pg_client = httpx.AsyncClient(
            base_url=f"{SUPABASE_URL}/rest/v1",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            },
            timeout=10.0,
        )
    return _pg_client


class _Rest:
    def __init__(self, path: str):
        self.path = path

    async def select(self, query: str) -> list[dict]:
        c = await _client()
        r = await c.get(f"{self.path}?{query}")
        r.raise_for_status()
        return r.json() or []

    async def insert(self, row: dict) -> dict:
        c = await _client()
        r = await c.post(
            self.path,
            json=row,
            headers={"Prefer": "return=representation,resolution=merge-duplicates"},
        )
        r.raise_for_status()
        return (r.json() or [{}])[0]

    async def update(self, query: str, row: dict) -> list[dict]:
        c = await _client()
        r = await c.post(f"{self.path}?{query}", json=row,
                         headers={"Prefer": "return=representation,resolution=merge-duplicates"})
        r.raise_for_status()
        return r.json() or []

    async def rpc(self, fn: str, args: dict) -> list[dict]:
        c = await _client()
        r = await c.post(f"/rpc/{fn}", json=args)
        r.raise_for_status()
        return r.json() or []


rest_profiles = _Rest("profiles")
rest_ledger = _Rest("ledger")
rest_rewards = _Rest("rewards")
rest_games = _Rest("stream_games")
rest_game_entries = _Rest("game_entries")
rest_giveaways = _Rest("giveaways")
rest_giveaway_entries = _Rest("giveaway_entries")
rest_custom_lb = _Rest("custom_leaderboard")
rest_live = _Rest("live_status")


_PROFILE_COLS = "user_id,discord_id,username,email,avatar_url,role,points_balance,created_at,updated_at"


def _row_to_user(row: dict) -> Optional[User]:
    if not row:
        return None
    return User(
        id=row.get("user_id"),
        discord_id=row["discord_id"],
        username=row.get("username") or "Anon",
        email=row.get("email"),
        avatar_url=row.get("avatar_url"),
        role=row.get("role") or "viewer",
        points_balance=int(row.get("points_balance") or 0),
    )


# ---------------- users ----------------

async def find_user_by_discord_id(discord_id: str) -> Optional[User]:
    rows = await rest_profiles.select(
        f"select={_PROFILE_COLS}&discord_id=eq.{discord_id}&limit=1")
    return _row_to_user(rows[0] if rows else None)


async def upsert_user_on_login(discord_id: str, username: str, email: Optional[str],
                               avatar_url: Optional[str], is_admin: bool) -> Optional[User]:
    """Called from the Supabase-token login path; mirrors legacy OAuth upsert."""
    existing = await find_user_by_discord_id(discord_id)
    now = datetime_iso()
    if existing:
        role = existing.role
        if is_admin and role not in ("owner", "admin"):
            role = "admin"
        await rest_profiles.update(
            f"user_id=eq.{existing.id}",
            {"username": username, "email": email, "avatar_url": avatar_url,
             "role": role, "updated_at": now},
        )
        return await find_user_by_discord_id(discord_id)
    role = "admin" if is_admin else "viewer"
    row = await rest_profiles.insert({
        "discord_id": discord_id, "username": username, "email": email,
        "avatar_url": avatar_url, "role": role, "points_balance": 0,
        "created_at": now, "updated_at": now,
    })
    return _row_to_user(row)


def datetime_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ---------------- ledger ----------------

async def ledger_recent(discord_id: str, limit: int) -> list[dict]:
    rows = await rest_ledger.select(
        f"select=delta,balance_after,reason,ref,created_at"
        f"&user_id=eq.{discord_id}&order=created_at.desc&limit={limit}"
    )
    return [{"delta": r["delta"], "balance_after": r["balance_after"],
             "reason": r["reason"], "ref": r.get("ref"), "created_at": r["created_at"]}
            for r in rows]


async def ledger_redemptions(discord_id: str) -> list[dict]:
    rows = await rest_ledger.select(
        f"select=delta,ref,created_at&user_id=eq.{discord_id}"
        f"&reason=eq.store_redeem&order=created_at.desc&limit=100"
    )
    # reward titles resolve by uuid ref
    titles: dict[str, str] = {}
    refs = {r.get("ref") for r in rows if r.get("ref")}
    if refs:
        id_list = ",".join(f"({x})" for x in refs)
        reward_rows = await rest_rewards.select(
            f"select=id,title&id=in.({','.join(refs)})")
        titles = {r["id"]: r["title"] for r in reward_rows}
    return [{"reward_title": titles.get(r.get("ref"), "Reward"),
             "cost": -int(r["delta"]), "created_at": r["created_at"]} for r in rows]


async def points_leaderboard(limit: int) -> list[dict]:
    rows = await rest_profiles.select(
        f"select=username,avatar_url,points_balance&points_balance=gt.0"
        f"&order=points_balance.desc&limit={limit}"
    )
    return [{"rank": i + 1, "username": r["username"], "avatar_url": r.get("avatar_url"),
             "points": int(r["points_balance"])} for i, r in enumerate(rows)]


# ---------------- store ----------------

async def rewards_active() -> list[dict]:
    rows = await rest_rewards.select(
        "select=id,title,description,cost,stock,image_url,category,requires"
        "&active=eq.true&order=cost.asc")
    return [{"id": r["id"], "title": r["title"], "description": r["description"],
             "cost": int(r["cost"]), "stock": int(r["stock"]),
             "image_url": r.get("image_url"), "category": r.get("category", "custom"),
             "requires": r.get("requires")} for r in rows]


async def redeem(user: User, reward_id: str, idempotency_key: str) -> dict:
    rows = await rest_profiles.rpc("redeem_reward", {
        "p_user_id": user.id, "p_reward_id": reward_id,
        "p_idempotency_key": idempotency_key,
    })
    row = rows[0] if rows else {}
    reason = row.get("reason")
    if reason == "redeemed":
        return {"ok": True, "balance_after": int(row["balance"])}
    if reason == "duplicate":
        return {"ok": True, "balance_after": int(row.get("balance") or 0)}
    mapping = {
        "reward_unavailable": (404, "Reward not found"),
        "out_of_stock": (400, "Out of stock"),
        "insufficient": (400, "Insufficient points"),
        "no_profile": (401, "User not found"),
    }
    status, msg = mapping.get(reason, (400, reason or "Redeem failed"))
    from fastapi import HTTPException
    raise HTTPException(status, msg)


# ---------------- games ----------------

async def games_list() -> list[dict]:
    rows = await rest_games.select(
        "select=id,title,kind,status,entry_cost,reward_pool,prompt,options,winning_option,created_at"
        "&order=created_at.desc&limit=50")
    return [{"id": r["id"], "title": r["title"], "kind": r["kind"], "status": r["status"],
             "entry_cost": int(r["entry_cost"]), "reward_pool": int(r["reward_pool"]),
             "prompt": r.get("prompt"), "options": r.get("options") or [],
             "winning_option": r.get("winning_option"), "created_at": r["created_at"]}
            for r in rows]


async def join_game(user: User, game_id: str, choice: Optional[str]) -> dict:
    rows = await rest_profiles.rpc("join_game", {
        "p_game_id": game_id, "p_user_id": user.id, "p_choice": choice,
        "p_username": user.username,
        "p_idempotency_key": f"ge_{game_id}_{user.discord_id}",
    })
    row = rows[0] if rows else {}
    reason = row.get("reason")
    if reason == "joined":
        return {"ok": True, "balance_after": int(row["balance"])}
    mapping = {
        "not_found": (404, "Game not found"),
        "closed": (400, "Game closed"),
        "invalid_choice": (400, "Choice must match one of the game options"),
        "already_joined": (400, "Already joined"),
        "insufficient": (400, "Insufficient points"),
        "no_profile": (401, "User not found"),
    }
    status, msg = mapping.get(reason, (400, reason or "Join failed"))
    from fastapi import HTTPException
    raise HTTPException(status, msg)


# ---------------- giveaways ----------------

async def giveaways_list() -> list[dict]:
    rows = await rest_giveaways.select(
        "select=id,title,description,prize,image_url,max_winners,status,ends_at,winners,created_at"
        "&order=created_at.desc&limit=50")
    counts: dict[str, int] = {}
    if rows:
        ids = [r["id"] for r in rows]
        entries = await rest_giveaway_entries.select(
            f"select=giveaway_id&giveaway_id=in.({','.join(ids)})")
        for e in entries:
            counts[e["giveaway_id"]] = counts.get(e["giveaway_id"], 0) + 1
    return [{"id": r["id"], "title": r["title"], "description": r["description"],
             "prize": r["prize"], "image_url": r.get("image_url"),
             "max_winners": int(r.get("max_winners") or 1), "status": r["status"],
             "ends_at": r.get("ends_at"), "winners": r.get("winners") or [],
             "entries": counts.get(r["id"], 0), "created_at": r["created_at"]}
            for r in rows]


async def enter_giveaway(user: User, giveaway_id: str) -> dict:
    rows = await rest_profiles.rpc("enter_giveaway", {
        "p_giveaway_id": giveaway_id, "p_user_id": user.id,
        "p_username": user.username,
    })
    row = rows[0] if rows else {}
    reason = row.get("reason")
    if reason == "entered":
        return {"ok": True, "entries": int(row["entries"])}
    mapping = {
        "not_found": (404, "Giveaway not found"),
        "closed": (400, "Giveaway closed"),
        "already_entered": (400, "Already entered"),
    }
    status, msg = mapping.get(reason, (400, reason or "Enter failed"))
    from fastapi import HTTPException
    raise HTTPException(status, msg)


# ---------------- custom leaderboard ----------------

async def custom_lb_list(board: Optional[str] = None) -> list[dict]:
    q = ("select=id,display_name,wagered,bets,board,note&order=wagered.desc&limit=500"
         + (f"&board=eq.{board}" if board else ""))
    rows = await rest_custom_lb.select(q)
    return [{"id": r["id"], "display_name": r["display_name"], "wagered": float(r["wagered"]),
             "bets": int(r.get("bets") or 0), "board": r.get("board", "monthly"),
             "note": r.get("note")} for r in rows]


# ---------------- watch beat ----------------

async def watch_beat(user: User, bucket: int, daily_cap: int) -> dict:
    rows = await rest_profiles.rpc("watch_beat", {
        "p_user_id": user.id, "p_bucket": bucket, "p_daily_cap": daily_cap,
    })
    row = rows[0] if rows else {}
    reason = row.get("reason")
    if reason == "awarded":
        return {"ok": True, "balance_after": int(row["balance"])}
    return {"ok": False, "reason": reason or "error"}


# ---------------- admin ----------------

async def admin_grant(discord_id: str, delta: int, reason: str,
                      idempotency_key: Optional[str]) -> dict:
    user = await find_user_by_discord_id(discord_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")
    rows = await rest_profiles.rpc("award_points", {
        "p_user_id": user.id, "p_delta": delta, "p_reason": reason,
        "p_ref": None, "p_idempotency_key": idempotency_key, "p_cooldown_sec": 0,
    })
    row = rows[0] if rows else {}
    if row.get("reason") in ("awarded", "duplicate"):
        return {"ok": True, "balance_after": int(row.get("balance") or 0)}
    from fastapi import HTTPException
    raise HTTPException(400, row.get("reason") or "grant failed")


async def admin_revoke(discord_id: str) -> dict:
    user = await find_user_by_discord_id(discord_id)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")
    rows = await rest_profiles.rpc("revoke_last_admin_grant", {"p_user_id": user.id})
    row = rows[0] if rows else {}
    if row.get("reason") == "awarded":
        return {"ok": True, "balance_after": int(row["balance"]), "revoked": True}
    from fastapi import HTTPException
    msg = {"no_grant": "No admin grant to revoke for this user",
           "no_op": "Last admin grant is a no-op",
           "duplicate": "Already revoked"}.get(row.get("reason"), "Revoke failed")
    raise HTTPException(400, msg)


async def admin_users_list(limit: int = 1000) -> list[dict]:
    rows = await rest_profiles.select(
        f"select={_PROFILE_COLS}&order=points_balance.desc&limit={limit}")
    return [{"discord_id": r["discord_id"], "username": r["username"],
             "avatar_url": r.get("avatar_url"), "role": r["role"],
             "points_balance": int(r["points_balance"])} for r in rows]


async def chat_award(discord_id: str, source: str, platform_username: str,
                     event_id: str, cooldown_seconds: int) -> dict:
    """Mirror of the Mongo chat-award flow for the internal endpoint."""
    user = await find_user_by_discord_id(discord_id)
    if not user:
        return {"awarded": False, "reason": "no_account"}
    rows = await rest_profiles.rpc("award_points", {
        "p_user_id": user.id, "p_delta": 1, "p_reason": f"chat_{source}",
        "p_ref": f"platform:{platform_username}",
        "p_idempotency_key": f"chat_{source}_{event_id}",
        "p_cooldown_sec": cooldown_seconds,
    })
    row = rows[0] if rows else {}
    reason = row.get("reason")
    if reason == "awarded":
        return {"awarded": True, "balance": int(row["balance"])}
    return {"awarded": False, "reason": reason or "error"}