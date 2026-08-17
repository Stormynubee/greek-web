"""Local-first regression and concurrency coverage for the public API."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import time
import uuid

import jwt
import pytest
import requests
from dotenv import load_dotenv
from bson import ObjectId
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / "backend" / ".env")
load_dotenv(REPO_ROOT / "frontend" / ".env")

BACKEND_URL = (
    os.getenv("BACKEND_API_URL")
    or os.getenv("API_URL")
    or "http://localhost:8000"
).rstrip("/")
API = BACKEND_URL if BACKEND_URL.endswith("/api") else f"{BACKEND_URL}/api"
JWT_SECRET = os.getenv("JWT_SECRET", "test-secret")
MONGO_URL = os.getenv(
    "MONGO_URL", "mongodb://localhost:27017/greekgodberry?replicaSet=rs0"
)
DB_NAME = os.getenv("DB_NAME", "greekgodberry")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

try:
    mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
    mongo.admin.command("ping")
    db = mongo[DB_NAME]
    MONGO_ERROR = None
except Exception as exc:  # pragma: no cover - setup guidance for local runs
    mongo = None
    db = None
    MONGO_ERROR = exc


@pytest.fixture(autouse=True)
def require_local_mongo():
    if MONGO_ERROR:
        pytest.skip(f"MongoDB is unavailable; start Docker MongoDB first: {MONGO_ERROR}")


def mint(discord_id):
    now = int(time.time())
    return jwt.encode(
        {"sub": discord_id, "iat": now, "exp": now + 3600},
        JWT_SECRET,
        algorithm="HS256",
    )


def admin_session():
    session = requests.Session()
    response = session.post(
        f"{API}/admin/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return session


def seed_user(discord_id, points=100):
    now = datetime.now(timezone.utc).isoformat()
    db.users.delete_many({"discord_id": discord_id})
    db.users.insert_one(
        {
            "discord_id": discord_id,
            "username": discord_id,
            "email": f"{discord_id}@example.com",
            "role": "viewer",
            "points_balance": points,
            "created_at": now,
            "updated_at": now,
        }
    )


def test_health_reports_database():
    response = requests.get(f"{API}/health", timeout=10)
    assert response.status_code == 200, response.text
    assert response.json()["database"] == "ok"


def test_cors_allows_configured_origin_only():
    response = requests.options(
        f"{API}/auth/me",
        headers={
            "Origin": FRONTEND_URL,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == FRONTEND_URL


def test_admin_cookie_uses_configured_security_mode():
    session = admin_session()
    cookie_header = session.post(
        f"{API}/admin/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    ).headers.get("set-cookie", "").lower()
    expected_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    expected_samesite = os.getenv(
        "COOKIE_SAMESITE", "none" if expected_secure else "lax"
    ).lower()
    assert "ggb_admin=" in cookie_header
    assert f"samesite={expected_samesite}" in cookie_header
    assert ("; secure" in cookie_header) is expected_secure


def test_discord_oauth_rejects_invalid_state():
    session = requests.Session()
    login = session.get(f"{API}/auth/discord/login")
    assert login.status_code == 200
    callback = session.get(
        f"{API}/auth/discord/callback",
        params={"code": "not-exchanged", "state": "wrong-state"},
        allow_redirects=False,
    )
    assert callback.status_code in (302, 303, 307, 308)
    assert "auth=error" in callback.headers["location"]


def test_discord_owner_can_access_owner_console():
    owner_id = f"regression_owner_{uuid.uuid4().hex}"
    seed_user(owner_id)
    db.users.update_one({"discord_id": owner_id}, {"$set": {"role": "owner"}})
    try:
        response = requests.get(
            f"{API}/admin/users", cookies={"ggb_session": mint(owner_id)}
        )
        assert response.status_code == 200, response.text
    finally:
        db.users.delete_many({"discord_id": owner_id})


def test_concurrent_redemptions_consume_one_stock_and_one_balance_debit():
    user_id = f"regression_redeem_{uuid.uuid4().hex}"
    seed_user(user_id, points=100)
    admin = admin_session()
    reward = admin.post(
        f"{API}/admin/rewards",
        json={"title": user_id, "description": "concurrency", "cost": 10, "stock": 1},
    )
    assert reward.status_code == 200, reward.text
    reward_id = reward.json()["id"]
    try:
        cookies = {"ggb_session": mint(user_id)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(
                    lambda _: requests.post(
                        f"{API}/store/redeem",
                        json={"reward_id": reward_id, "idempotency_key": f"{user_id}_{uuid.uuid4().hex}"},
                        cookies=cookies,
                    ),
                    range(4),
                )
            )
        assert sum(response.status_code == 200 for response in responses) == 1
        assert sum(response.status_code == 400 for response in responses) == 3
        assert db.users.find_one({"discord_id": user_id})["points_balance"] == 90
        assert db.rewards.find_one({"_id": ObjectId(reward_id)})["stock"] == 0
    finally:
        db.rewards.delete_one({"_id": ObjectId(reward_id)})
        db.users.delete_many({"discord_id": user_id})
        db.ledger.delete_many({"user_id": user_id})


def test_concurrent_game_joins_create_one_entry_and_one_debit():
    user_id = f"regression_game_{uuid.uuid4().hex}"
    seed_user(user_id, points=100)
    admin = admin_session()
    game = admin.post(
        f"{API}/admin/games",
        json={
            "title": user_id,
            "kind": "prediction",
            "options": ["yes", "no"],
            "entry_cost": 10,
            "reward_pool": 20,
        },
    )
    assert game.status_code == 200, game.text
    game_id = game.json()["id"]
    try:
        cookies = {"ggb_session": mint(user_id)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(
                pool.map(
                    lambda _: requests.post(
                        f"{API}/games/join",
                        json={"game_id": game_id, "choice": "yes"},
                        cookies=cookies,
                    ),
                    range(4),
                )
            )
        assert sum(response.status_code == 200 for response in responses) == 1
        assert sum(response.status_code == 400 for response in responses) == 3
        assert db.users.find_one({"discord_id": user_id})["points_balance"] == 90
        assert db.game_entries.count_documents({"game_id": game_id, "user_id": user_id}) == 1
    finally:
        db.games.delete_one({"_id": ObjectId(game_id)})
        db.users.delete_many({"discord_id": user_id})
        db.ledger.delete_many({"user_id": user_id})
        db.game_entries.delete_many({"game_id": game_id, "user_id": user_id})
