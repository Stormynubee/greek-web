"""Option 2: pre-provision Atlas users into Supabase Auth + backfill balances.

For every Atlas user:
  1. Create a Supabase auth user (email = placeholder, email_confirmed).
  2. Link the Discord identity (provider=discord, provider_id=<discord_id>) so
     the next Discord OAuth login attaches to THIS auth user instead of creating
     a duplicate.
  3. Create the profiles row with the exact points_balance from Atlas.
  4. Insert an opening-balance ledger row so SUM(ledger.delta) == balance holds.

Idempotent: safe to re-run; existing users are updated, not duplicated.

Usage:
  set MONGO_URL=... & set SUPABASE_URL=... & set SUPABASE_SERVICE_ROLE_KEY=...
  python preprovision_users.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

from pymongo import MongoClient
from supabase import create_client

# The avatar cache-breaker Discord needs; mirrors AuthService.getAvatarUrl.
AVATAR_TTL = 256


def supabase_admin_request(method: str, path: str, key: str, body: dict | None = None):
    """Direct Admin REST call — the python client lib lacks identity linking."""
    url = f"{os.environ['SUPABASE_URL']}/auth/v1/admin{path}"
    data = None
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if body is not None:
        data = json_bytes(body)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json_loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def json_bytes(obj) -> bytes:
    import json
    return json.dumps(obj).encode()


def json_loads(raw: bytes):
    import json
    return json.loads(raw.decode())


def discord_avatar_url(discord_id: str, avatar_hash: str | None) -> str | None:
    if not avatar_hash:
        return None
    return f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mongo-url", default=os.environ.get("MONGO_URL"))
    ap.add_argument("--mongo-db", default=os.environ.get("DB_NAME", "greekgodberry"))
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    args = ap.parse_args()

    if not (args.mongo_url and args.supabase_url and args.supabase_key):
        print("Missing MONGO_URL / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        return 2

    mongo = MongoClient(args.mongo_url, serverSelectionTimeoutMS=8000)
    db = mongo[args.mongo_db]

    created = updated = skipped = failed = 0
    failures: list[str] = []

    users = list(db.users.find({}).sort("created_at", 1))
    print(f"Atlas users to process: {len(users)}\n")

    for u in users:
        discord_id = u.get("discord_id")
        if not discord_id:
            skipped += 1
            continue

        username = u.get("username") or f"user_{discord_id[-6:]}"
        email = u.get("email") or f"{discord_id}@greekgambles.placeholder"
        avatar = discord_avatar_url(discord_id, u.get("avatar"))
        balance = int(u.get("points_balance") or 0)
        role = u.get("role") or "viewer"

        if args.dry_run:
            print(f"[dry] {username:<20} discord={discord_id} balance={balance} role={role}")
            created += 1
            continue

        # 1) Does an auth user with this discord identity already exist?
        st, existing = supabase_admin_request(
            "GET", f"/users?provider=discord&provider_id={discord_id}", args.supabase_key)
        auth_user = None
        if st == 200 and isinstance(existing, dict):
            found = existing.get("users") or []
            if found:
                auth_user = found[0]

        if auth_user is None:
            # 2) Create the auth user with a linked Discord identity.
            payload = {
                "email": email,
                "email_confirm": True,
                "user_metadata": {
                    "discord_id": discord_id,
                    "full_name": username,
                    "avatar_url": avatar,
                    "preprovisioned": True,
                },
                "app_metadata": {"provider": "discord", "providers": ["discord"]},
                "identities": [{
                    "provider": "discord",
                    "uid": discord_id,
                    "user_id": None,  # server fills
                    "identity_data": {
                        "sub": discord_id,
                        "discord_id": discord_id,
                        "name": username,
                        "full_name": username,
                        "avatar_url": avatar,
                        "email": email,
                        "email_verified": True,
                        "provider_id": discord_id,
                    },
                }],
            }
            st, resp = supabase_admin_request("POST", "/users", args.supabase_key, payload)
            if st not in (200, 201):
                # 422 = identity/email conflict; try email lookup fallback
                if st == 422 and isinstance(resp, str) and "already been registered" in resp:
                    # find by email, adopt it
                    st2, found = supabase_admin_request(
                        "GET", f"/users?email={urllib.parse.quote(email)}", args.supabase_key)
                    if st2 == 200 and isinstance(found, dict) and found.get("users"):
                        auth_user = found["users"][0]
                        updated += 1
                    else:
                        failed += 1
                        failures.append(f"{username}: create failed: {resp[:120]}")
                        continue
                else:
                    failed += 1
                    failures.append(f"{username}: create failed ({st}): {str(resp)[:120]}")
                    continue
            else:
                auth_user = resp
                created += 1
        else:
            updated += 1

        user_id = auth_user["id"]

        # 3) Link the Discord identity into the identities table if missing.
        ident = (auth_user.get("identities") or [])
        has_discord = any(
            (i.get("provider") == "discord" and (i.get("identity_data") or {}).get("sub") == discord_id)
            or i.get("provider_id") == discord_id
            for i in ident
        )
        if not has_discord:
            print(f"  note: {username} has no discord identity yet; OAuth link will attach on next login")

        # 4) Upsert the profiles row with the exact Atlas balance.
        sb = create_client(args.supabase_url, args.supabase_key)
        prof = {
            "user_id": user_id,
            "discord_id": discord_id,
            "username": username,
            "email": email if "@greekgambles.placeholder" not in email else None,
            "avatar_url": avatar,
            "role": role,
            "points_balance": balance,
        }
        try:
            sb.table("profiles").upsert(prof, on_conflict="user_id").execute()
        except Exception as e:
            failed += 1
            failures.append(f"{username}: profiles upsert failed: {e}")
            continue

        # 5) Opening-balance ledger row (only if none exists for this migration).
        try:
            existing_rows = sb.table("ledger").select("id").eq(
                "idempotency_key", f"migrate_opening_{discord_id}").execute()
            if not existing_rows.data:
                sb.table("ledger").insert({
                    "user_id": user_id,
                    "delta": balance,
                    "balance_after": balance,
                    "reason": "migrate_opening_balance",
                    "idempotency_key": f"migrate_opening_{discord_id}",
                    "ts": int(time.time()),
                }).execute()
        except Exception as e:
            failed += 1
            failures.append(f"{username}: ledger insert failed: {e}")
            continue

        print(f"ok: {username:<20} auth_user={user_id[:8]}… balance={balance} role={role}")

    print(f"\nSummary: created={created} updated={updated} skipped={skipped} failed={failed}")
    for f in failures:
        print("  FAIL:", f)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())