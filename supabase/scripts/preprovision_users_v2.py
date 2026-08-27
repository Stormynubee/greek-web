"""Option 2 (v2): create the remaining Atlas users in Supabase Auth + backfill.

Fixed lookup: an existing auth user is ONLY matched by exact email equality.
Never falls back to an unrelated user. Safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

from pymongo import MongoClient


def admin_req(method, path, key, body=None):
    url = f"{os.environ['SUPABASE_URL']}/auth/v1/admin{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("apikey", key)
    r.add_header("Authorization", f"Bearer {key}")
    if body is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def rest_req(method, path, key, body=None):
    url = f"{os.environ['SUPABASE_URL']}/rest/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("apikey", key)
    r.add_header("Authorization", f"Bearer {key}")
    if body is not None:
        r.add_header("Content-Type", "application/json")
        r.add_header("Prefer", "return=representation,resolution=merge-duplicates")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo-url", default=os.environ.get("MONGO_URL"))
    ap.add_argument("--mongo-db", default=os.environ.get("DB_NAME", "greekgodberry"))
    ap.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    ap.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    ap.add_argument("--skip-discord-id", default="940509012649181184",
                    help="Already-migrated Discord ID (real login user) to skip")
    args = ap.parse_args()

    mongo = MongoClient(args.mongo_url, serverSelectionTimeoutMS=8000)
    db = mongo[args.mongo_db]
    key = args.supabase_key

    created = failed = skipped = 0
    failures = []
    users = list(db.users.find({}).sort("created_at", 1))
    print(f"Atlas users: {len(users)} (skipping discord_id={args.skip_discord_id})\n")

    for u in users:
        discord_id = u.get("discord_id")
        if not discord_id or discord_id == args.skip_discord_id:
            skipped += 1
            continue

        username = u.get("username") or f"user_{discord_id[-6:]}"
        email = u.get("email") or f"{discord_id}@greekgambles.placeholder"
        balance = int(u.get("points_balance") or 0)
        role = u.get("role") or "viewer"

        # Only exact-email match counts as "exists".
        st, found = admin_req("GET", f"/users?email={urllib.parse.quote(email)}", key)
        auth_user = None
        if st == 200 and isinstance(found, dict):
            for cand in found.get("users", []):
                if (cand.get("email") or "").lower() == email.lower():
                    auth_user = cand
                    break

        if auth_user is None:
            payload = {
                "email": email,
                "email_confirm": True,
                "user_metadata": {
                    "discord_id": discord_id,
                    "full_name": username,
                    "preprovisioned": True,
                },
                "app_metadata": {"provider": "discord", "providers": ["discord"]},
                "identities": [{
                    "provider": "discord",
                    "uid": discord_id,
                    "identity_data": {
                        "sub": discord_id,
                        "discord_id": discord_id,
                        "name": username,
                        "provider_id": discord_id,
                    },
                }],
            }
            st, resp = admin_req("POST", "/users", key, payload)
            if st in (200, 201) and isinstance(resp, dict):
                auth_user = resp
                action = "created"
            else:
                failed += 1
                failures.append(f"{username}: {st} {str(resp)[:140]}")
                continue
        else:
            action = "existing"

        uid = auth_user["id"]

        # Upsert: the handle_new_user trigger creates a profile on auth-user
        # creation, so insert collides. Update that row with real balance/role.
        st, body = rest_req("POST", "/profiles?on_conflict=user_id", key, {
            "user_id": uid,
            "discord_id": discord_id,
            "username": username,
            "role": role,
            "points_balance": balance,
        })
        if st not in (200, 201):
            # PostgREST upsert needs the Prefer=resolution header; fall back to PATCH.
            st, body = rest_req("PATCH", f"/profiles?user_id=eq.{uid}", key, {
                "discord_id": discord_id,
                "username": username,
                "role": role,
                "points_balance": balance,
            })
        if st not in (200, 201, 204):
            failed += 1
            failures.append(f"{username}: profile {st} {str(body)[:100]}")
            continue

        st, dup = rest_req("GET", f"/ledger?select=id&idempotency_key=eq.migrate_opening_{discord_id}", key)
        if not dup:
            st, body = rest_req("POST", "/ledger", key, {
                "user_id": uid,
                "delta": balance,
                "balance_after": balance,
                "reason": "migrate_opening_balance",
                "idempotency_key": f"migrate_opening_{discord_id}",
                "ts": int(time.time()),
            })
            if st not in (200, 201):
                failed += 1
                failures.append(f"{username}: ledger {st} {str(body)[:100]}")
                continue

        created += 1
        print(f"ok [{action}] {username:<16} {discord_id}  bal={balance}  uid={uid[:8]}")

    print(f"\nSummary: processed={created} skipped={skipped} failed={failed}")
    for f in failures:
        print("  FAIL:", f)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())