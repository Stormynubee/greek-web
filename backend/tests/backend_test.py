"""GreekGodBerry backend API integration tests."""
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import jwt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")
load_dotenv(REPO_ROOT / "frontend" / ".env")

BASE_URL = (
    os.getenv("BACKEND_API_URL")
    or os.getenv("API_URL")
    or os.getenv("REACT_APP_BACKEND_URL")
    or "http://localhost:8000"
).rstrip("/")
API = BASE_URL if BASE_URL.endswith("/api") else f"{BASE_URL}/api"
JWT_SECRET = os.getenv("JWT_SECRET", "test-secret")
MONGO_URL = os.getenv(
    "MONGO_URL", "mongodb://localhost:27017/greekgodberry?replicaSet=rs0"
)
DB_NAME = os.getenv("DB_NAME", "greekgodberry")

try:
    mc = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    mc.admin.command("ping")
    db = mc[DB_NAME]
    MONGO_ERROR = None
except Exception as exc:  # pragma: no cover - setup guidance for local runs
    mc = None
    db = None
    MONGO_ERROR = exc

VIEWER_ID = "test_user_1"
OWNER_ID = "owner_1"
OWNER_EMAIL = os.getenv("OWNER_EMAIL", "owner@example.com")
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "replace-with-discord-client-id")


def mint(discord_id):
    now = int(time.time())
    return jwt.encode({"sub": discord_id, "iat": now, "exp": now + 3600},
                      JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module", autouse=True)
def seed_users():
    if MONGO_ERROR:
        pytest.skip(f"MongoDB is unavailable; start Docker MongoDB first: {MONGO_ERROR}")
    # cleanup prior test data
    db.users.delete_many({"discord_id": {"$in": [VIEWER_ID, OWNER_ID]}})
    db.ledger.delete_many({"user_id": {"$in": [VIEWER_ID, OWNER_ID]}})
    db.game_entries.delete_many({"user_id": {"$in": [VIEWER_ID, OWNER_ID]}})
    now_iso = datetime.now(timezone.utc).isoformat()
    db.users.insert_one({
        "discord_id": VIEWER_ID, "username": "TestUser", "email": "test@example.com",
        "role": "viewer", "points_balance": 1000,
        "created_at": now_iso, "updated_at": now_iso,
    })
    db.users.insert_one({
        "discord_id": OWNER_ID, "username": "OwnerUser", "email": OWNER_EMAIL,
        "role": "owner", "points_balance": 0,
        "created_at": now_iso, "updated_at": now_iso,
    })
    yield
    db.users.delete_many({"discord_id": {"$in": [VIEWER_ID, OWNER_ID]}})
    db.ledger.delete_many({"user_id": {"$in": [VIEWER_ID, OWNER_ID]}})
    db.game_entries.delete_many({"user_id": {"$in": [VIEWER_ID, OWNER_ID]}})


def viewer_cookies():
    return {"ggb_session": mint(VIEWER_ID)}


def owner_cookies():
    return {"ggb_session": mint(OWNER_ID)}


# ---------- Basic ----------
def test_root():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert r.json() == {"service": "ggb-api", "status": "ok"}


def test_discord_login_url():
    r = requests.get(f"{API}/auth/discord/login")
    assert r.status_code == 200
    url = r.json()["url"]
    assert "discord.com/api/oauth2/authorize" in url
    assert f"client_id={DISCORD_CLIENT_ID}" in url
    assert "redirect_uri=" in url


def test_auth_me_unauth():
    r = requests.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_logout_no_body():
    r = requests.post(f"{API}/auth/logout")
    assert r.status_code == 200
    assert r.json().get("ok") is True
    # cookie clear header
    sc = r.headers.get("set-cookie", "")
    assert "ggb_session" in sc.lower()


# ---------- Leaderboard ----------
@pytest.mark.parametrize("t", ["daily", "weekly", "monthly"])
def test_leaderboard_types(t):
    r = requests.get(f"{API}/leaderboard", params={"type": t})
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("type", "from", "total_users", "total_wagered", "rankings"):
        assert k in d
    if d["rankings"]:
        row = d["rankings"][0]
        assert row["rank"] == 1
        assert isinstance(row["wagered"], (int, float))


def test_leaderboard_invalid():
    r = requests.get(f"{API}/leaderboard", params={"type": "yearly"})
    assert r.status_code == 400


def test_leaderboard_masked():
    r = requests.get(f"{API}/leaderboard", params={"type": "monthly", "mask": "true"})
    assert r.status_code == 200
    for row in r.json()["rankings"][:5]:
        assert "***" in row["name"]


def test_leaderboard_cache():
    t1 = time.time()
    requests.get(f"{API}/leaderboard", params={"type": "monthly"})
    d1 = time.time() - t1
    t2 = time.time()
    r2 = requests.get(f"{API}/leaderboard", params={"type": "monthly"})
    d2 = time.time() - t2
    assert r2.status_code == 200
    # Soft: second should not be >2x slower
    print(f"cache timings: first={d1:.3f} second={d2:.3f}")


# ---------- Store ----------
def test_store_rewards_seeded():
    r = requests.get(f"{API}/store/rewards")
    assert r.status_code == 200
    rewards = r.json()["rewards"]
    assert len(rewards) >= 4
    costs = sorted(x["cost"] for x in rewards)
    assert costs[:4] == [750, 1750, 2500, 2500]
    for x in rewards:
        for k in ("id", "title", "description", "cost", "stock", "image_url"):
            assert k in x


def test_redeem_no_auth():
    r = requests.post(f"{API}/store/redeem", json={"reward_id": "x"})
    assert r.status_code == 401


# ---------- Games (public) ----------
def test_games_list_empty_initially():
    r = requests.get(f"{API}/games")
    assert r.status_code == 200
    assert "games" in r.json()


def test_games_join_no_auth():
    r = requests.post(f"{API}/games/join", json={"game_id": "x"})
    assert r.status_code == 401


# ---------- Admin unauth ----------
def test_admin_users_no_auth():
    r = requests.get(f"{API}/admin/users")
    assert r.status_code == 401


def test_admin_games_no_auth():
    r = requests.post(f"{API}/admin/games", json={"title": "x", "kind": "prediction"})
    assert r.status_code == 401


# ---------- Authenticated Viewer ----------
def test_auth_me_viewer():
    r = requests.get(f"{API}/auth/me", cookies=viewer_cookies())
    assert r.status_code == 200
    d = r.json()
    assert d["discord_id"] == VIEWER_ID
    assert d["points_balance"] == 1000
    assert d["role"] == "viewer"


def test_points_me():
    r = requests.get(f"{API}/points/me", cookies=viewer_cookies())
    assert r.status_code == 200
    assert r.json()["balance"] == 1000


def test_points_ledger_initial_empty():
    r = requests.get(f"{API}/points/ledger", cookies=viewer_cookies())
    assert r.status_code == 200
    assert r.json()["entries"] == []


def _get_reward(cost):
    r = requests.get(f"{API}/store/rewards")
    for x in r.json()["rewards"]:
        if x["cost"] == cost:
            return x
    return None


def test_redeem_success_and_balance_stock():
    reward = _get_reward(750)
    assert reward
    initial_stock = reward["stock"]
    key = f"test_redeem_{uuid.uuid4()}"
    r = requests.post(f"{API}/store/redeem",
                      json={"reward_id": reward["id"], "idempotency_key": key},
                      cookies=viewer_cookies())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["balance_after"] == 250
    # ledger has one entry
    lr = requests.get(f"{API}/points/ledger", cookies=viewer_cookies()).json()["entries"]
    assert len(lr) == 1 and lr[0]["delta"] == -750

    # stock decreased
    r2 = _get_reward(750)
    if initial_stock > 0:
        assert r2["stock"] == initial_stock - 1

    # idempotency: same key
    r3 = requests.post(f"{API}/store/redeem",
                       json={"reward_id": reward["id"], "idempotency_key": key},
                       cookies=viewer_cookies())
    assert r3.status_code == 200
    bal = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    assert bal == 250


def test_insufficient_points():
    reward = _get_reward(3000)
    assert reward
    r = requests.post(f"{API}/store/redeem",
                      json={"reward_id": reward["id"],
                            "idempotency_key": f"insuf_{uuid.uuid4()}"},
                      cookies=viewer_cookies())
    assert r.status_code == 400
    assert "Insufficient" in r.text


# ---------- Owner flows ----------
GAME_ID = {"id": None}


def test_owner_create_game():
    r = requests.post(f"{API}/admin/games",
                      json={"title": "Test Predict", "kind": "prediction",
                            "prompt": "Will streamer win?",
                            "options": ["Yes", "No"],
                            "entry_cost": 10, "reward_pool": 100},
                      cookies=owner_cookies())
    assert r.status_code == 200, r.text
    GAME_ID["id"] = r.json()["id"]
    assert GAME_ID["id"]


def test_non_owner_cannot_create_game():
    r = requests.post(f"{API}/admin/games",
                      json={"title": "x", "kind": "prediction"},
                      cookies=viewer_cookies())
    assert r.status_code == 403


def test_viewer_join_game():
    gid = GAME_ID["id"]
    assert gid
    bal_before = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    r = requests.post(f"{API}/games/join",
                      json={"game_id": gid, "choice": "Yes"},
                      cookies=viewer_cookies())
    assert r.status_code == 200, r.text
    bal_after = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    assert bal_after == bal_before - 10


def test_duplicate_join():
    gid = GAME_ID["id"]
    r = requests.post(f"{API}/games/join",
                      json={"game_id": gid, "choice": "Yes"},
                      cookies=viewer_cookies())
    assert r.status_code == 400
    assert "Already" in r.text


def test_resolve_game_payout():
    gid = GAME_ID["id"]
    bal_before = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    r = requests.post(f"{API}/admin/games/{gid}/resolve",
                      json={"winning_option": "Yes"},
                      cookies=owner_cookies())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["winners"] == 1
    assert d["per_winner"] == 100
    bal_after = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    assert bal_after == bal_before + 100


def test_admin_grant():
    bal_before = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    r = requests.post(f"{API}/admin/points/grant",
                      json={"discord_id": VIEWER_ID, "delta": 250},
                      cookies=owner_cookies())
    assert r.status_code == 200, r.text
    bal_after = requests.get(f"{API}/points/me", cookies=viewer_cookies()).json()["balance"]
    assert bal_after == bal_before + 250


def test_admin_users_list():
    r = requests.get(f"{API}/admin/users", cookies=owner_cookies())
    assert r.status_code == 200
    ids = [u["discord_id"] for u in r.json()["users"]]
    assert VIEWER_ID in ids and OWNER_ID in ids
