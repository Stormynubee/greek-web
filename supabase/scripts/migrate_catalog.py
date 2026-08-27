"""Copy remaining catalog data Atlas -> Supabase (rewards, games, live_status).

Reads Atlas; upserts into Supabase Postgres. Idempotent: matches on natural
keys (rewards by title, games by title) and only inserts what's missing, then
syncs mutable fields.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from pymongo import MongoClient

SR = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SB = os.environ["SUPABASE_URL"]


def rest(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(SB + "/rest/v1" + path, data=data, method=method)
    r.add_header("apikey", SR)
    r.add_header("Authorization", f"Bearer {SR}")
    if body is not None:
        r.add_header("Content-Type", "application/json")
        r.add_header("Prefer", "return=representation,resolution=merge-duplicates")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def iso(dt):
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return dt


def main():
    mongo = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)
    db = mongo[os.environ.get("DB_NAME", "greekgodberry")]

    # ---- rewards (upsert by title via PATCH loop; small dataset) ----
    existing = rest("GET", "/rewards?select=id,title")[1] or []
    by_title = {r["title"]: r["id"] for r in existing}
    n = 0
    for r in db.rewards.find({}):
        row = {
            "title": r["title"],
            "description": r.get("description", ""),
            "cost": int(r.get("cost", 0)),
            "stock": int(r.get("stock", 0)),
            "image_url": r.get("image_url"),
            "active": bool(r.get("active", True)),
            "category": r.get("category", "custom"),
            "requires": r.get("requires"),
            "created_at": iso(r.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        }
        if r["title"] in by_title:
            st, _ = rest("PATCH", f"/rewards?id=eq.{by_title[r['title']]}", row)
        else:
            st, _ = rest("POST", "/rewards", row)
        if st in (200, 201, 204):
            n += 1
        else:
            print(f"  reward FAIL {r['title']}: {st}")
    print(f"rewards synced: {n}")

    # ---- games -> stream_games (upsert by title) ----
    existing = rest("GET", "/stream_games?select=id,title")[1] or []
    by_title = {g["title"]: g["id"] for g in existing}
    n = 0
    for g in db.games.find({}):
        row = {
            "title": g["title"],
            "kind": g.get("kind", "raffle"),
            "status": g.get("status", "open"),
            "entry_cost": int(g.get("entry_cost", 0)),
            "reward_pool": int(g.get("reward_pool", 0)),
            "prompt": g.get("prompt"),
            "options": g.get("options") or [],
            "winning_option": g.get("winning_option"),
            "created_at": iso(g.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        }
        if g["title"] in by_title:
            st, _ = rest("PATCH", f"/stream_games?id=eq.{by_title[g['title']]}", row)
        else:
            st, _ = rest("POST", "/stream_games", row)
        if st in (200, 201, 204):
            n += 1
        else:
            print(f"  game FAIL {g['title']}: {st}")
    print(f"games synced: {n}")

    # ---- custom_leaderboard (insert-only; dataset empty today) ----
    count = rest("GET", "/custom_leaderboard?select=id", )[1]
    have = len(count or [])
    want = db.custom_leaderboard.count_documents({})
    print(f"custom_leaderboard: supabase={have} atlas={want} ({'ok' if have >= want else 'NEEDS SYNC'})")

    # ---- live_status (single row) ----
    ls = db.live_status.find_one()
    if ls:
        row = {
            "is_live": bool(ls.get("is_live", False)),
            "platform": ls.get("platform", "kick"),
            "title": ls.get("title"),
            "url": ls.get("url") or "https://kick.com/greekgodberry",
        }
        st, _ = rest("PATCH", "/live_status?id=eq.true", row)
        print("live_status synced:", st)

    # ---- giveaways + entries (insert-only; dataset empty today) ----
    gw = db.giveaways.count_documents({})
    have = len(rest("GET", "/giveaways?select=id")[1] or [])
    print(f"giveaways: supabase={have} atlas={gw} ({'ok' if have >= gw else 'NEEDS SYNC'})")

    print("\ncatalog migration done.")


if __name__ == "__main__":
    main()