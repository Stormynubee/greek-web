"""Iteration 3: admin auth, giveaways, custom leaderboard, live status, point shop tabs."""
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
import jwt
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
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")

mc = MongoClient(MONGO_URL)
db = mc[DB_NAME]

VIEWER_ID = "iter3_viewer"


def mint(discord_id):
    now = int(time.time())
    return jwt.encode({"sub": discord_id, "iat": now, "exp": now + 3600},
                      JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="module", autouse=True)
def seed():
    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    db.users.delete_many({"discord_id": VIEWER_ID})
    db.users.insert_one({
        "discord_id": VIEWER_ID, "username": "Iter3Viewer",
        "email": "iter3@example.com", "role": "viewer", "points_balance": 500,
        "created_at": now_iso, "updated_at": now_iso,
    })
    # Clear only this configured account's old lockout state.
    db.admin_login_attempts.delete_many({
        "identifier": {"$in": [f"user:{ADMIN_USERNAME.lower()}", "ip:127.0.0.1"]}
    })
    yield
    db.users.delete_many({"discord_id": VIEWER_ID})
    db.giveaway_entries.delete_many({"user_id": VIEWER_ID})


def viewer_cookies():
    return {"ggb_session": mint(VIEWER_ID)}


# ---------- Admin auth ----------
def test_admin_login_wrong_creds():
    r = requests.post(f"{API}/admin/login",
                      json={"username": ADMIN_USERNAME, "password": "wrong-pw-xyz"})
    assert r.status_code == 401


def test_admin_login_success_and_me():
    s = requests.Session()
    r = s.post(f"{API}/admin/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert d.get("username") == ADMIN_USERNAME
    assert "ggb_admin" in s.cookies

    me = s.get(f"{API}/admin/me")
    assert me.status_code == 200
    assert me.json()["username"] == ADMIN_USERNAME

    lo = s.post(f"{API}/admin/logout")
    assert lo.status_code == 200


def test_admin_me_no_cookie():
    r = requests.get(f"{API}/admin/me")
    assert r.status_code == 401


def test_admin_brute_force_lockout():
    brute_username = f"brute_{uuid.uuid4().hex}"
    configured_admin = db.admin_accounts.find_one({"username": ADMIN_USERNAME})
    assert configured_admin
    db.admin_accounts.insert_one({
        "username": brute_username,
        "password_hash": configured_admin["password_hash"],
    })
    try:
        for _ in range(5):
            requests.post(
                f"{API}/admin/login",
                json={"username": brute_username, "password": "bad"},
            )
        r = requests.post(
            f"{API}/admin/login",
            json={"username": brute_username, "password": "bad"},
        )
        assert r.status_code == 429, r.text
    finally:
        db.admin_accounts.delete_one({"username": brute_username})
        db.admin_login_attempts.delete_many({"identifier": {"$regex": brute_username}})


# ---------- Admin session helper ----------
@pytest.fixture
def admin_sess():
    s = requests.Session()
    r = s.post(f"{API}/admin/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return s


# ---------- Live status ----------
def test_live_initial_shape():
    r = requests.get(f"{API}/live")
    assert r.status_code == 200
    d = r.json()
    for k in ("is_live", "platform", "url"):
        assert k in d


def test_admin_set_live_and_read(admin_sess):
    r = admin_sess.post(f"{API}/admin/live",
                        json={"is_live": True, "url": "https://kick.com/greekgodberry",
                              "title": "Live now"})
    assert r.status_code == 200
    pub = requests.get(f"{API}/live").json()
    assert pub["is_live"] is True
    assert pub["url"] == "https://kick.com/greekgodberry"
    # Reset to false
    admin_sess.post(f"{API}/admin/live",
                    json={"is_live": False, "url": "https://kick.com/greekgodberry"})
    assert requests.get(f"{API}/live").json()["is_live"] is False


# ---------- Giveaways ----------
GIVEAWAY = {"id": None}


def test_admin_create_giveaway(admin_sess):
    r = admin_sess.post(f"{API}/admin/giveaways",
                        json={"title": "TEST_Giveaway", "description": "for testing",
                              "prize": "TEST prize", "max_winners": 2})
    assert r.status_code == 200, r.text
    GIVEAWAY["id"] = r.json()["id"]


def test_public_giveaways_lists_it():
    r = requests.get(f"{API}/giveaways")
    assert r.status_code == 200
    ids = [g["id"] for g in r.json()["giveaways"]]
    assert GIVEAWAY["id"] in ids
    g = next(g for g in r.json()["giveaways"] if g["id"] == GIVEAWAY["id"])
    assert g["entries"] == 0


def test_enter_giveaway_and_duplicate():
    r = requests.post(f"{API}/giveaways/enter",
                      json={"giveaway_id": GIVEAWAY["id"]},
                      cookies=viewer_cookies())
    assert r.status_code == 200, r.text
    assert r.json()["entries"] >= 1

    r2 = requests.post(f"{API}/giveaways/enter",
                       json={"giveaway_id": GIVEAWAY["id"]},
                       cookies=viewer_cookies())
    assert r2.status_code == 400
    assert "already" in r2.text.lower()


def test_enter_giveaway_unauth():
    r = requests.post(f"{API}/giveaways/enter",
                     json={"giveaway_id": GIVEAWAY["id"]})
    assert r.status_code == 401


def test_admin_draw_giveaway(admin_sess):
    r = admin_sess.post(f"{API}/admin/giveaways/{GIVEAWAY['id']}/draw")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert isinstance(d["winners"], list) and len(d["winners"]) >= 1
    # status persisted
    g = next(g for g in requests.get(f"{API}/giveaways").json()["giveaways"]
             if g["id"] == GIVEAWAY["id"])
    assert g["status"] == "drawn"


def test_admin_close_giveaway(admin_sess):
    # create fresh one to close (drawn one can't be re-closed cleanly)
    r = admin_sess.post(f"{API}/admin/giveaways",
                        json={"title": "TEST_close", "description": "x",
                              "prize": "y", "max_winners": 1})
    gid = r.json()["id"]
    cr = admin_sess.post(f"{API}/admin/giveaways/{gid}/close")
    assert cr.status_code == 200
    g = next(g for g in requests.get(f"{API}/giveaways").json()["giveaways"]
             if g["id"] == gid)
    assert g["status"] == "closed"


# ---------- Custom leaderboard ----------
CUSTOM = {"id": None}


def test_admin_create_custom_lb(admin_sess):
    r = admin_sess.post(f"{API}/admin/custom-leaderboard",
                        json={"display_name": "TEST_Ghost1", "wagered": 999999,
                              "bets": 10, "board": "monthly"})
    assert r.status_code == 200, r.text
    CUSTOM["id"] = r.json()["id"]


def test_leaderboard_includes_custom():
    r = requests.get(f"{API}/leaderboard", params={"type": "monthly"})
    assert r.status_code == 200
    rankings = r.json()["rankings"]
    ghost = [x for x in rankings if x["name"] == "TEST_Ghost1"]
    assert ghost, "Custom entry missing from merged monthly leaderboard"
    # Since wagered=999999 (very high), it should be rank 1
    assert ghost[0]["rank"] == 1
    assert ghost[0]["source"] == "custom"


def test_admin_delete_custom_lb(admin_sess):
    r = admin_sess.delete(f"{API}/admin/custom-leaderboard/{CUSTOM['id']}")
    assert r.status_code == 200
    rankings = requests.get(f"{API}/leaderboard", params={"type": "monthly"}).json()["rankings"]
    assert not any(x["name"] == "TEST_Ghost1" for x in rankings)


# ---------- Rewards admin ----------
def test_admin_create_and_delete_reward(admin_sess):
    r = admin_sess.post(f"{API}/admin/rewards",
                        json={"title": "TEST_reward", "description": "x",
                              "cost": 100, "stock": 5})
    assert r.status_code == 200
    rid = r.json()["id"]
    # visible via public
    rewards = requests.get(f"{API}/store/rewards").json()["rewards"]
    assert any(x["id"] == rid for x in rewards)
    # delete → not visible
    d = admin_sess.delete(f"{API}/admin/rewards/{rid}")
    assert d.status_code == 200
    rewards2 = requests.get(f"{API}/store/rewards").json()["rewards"]
    assert not any(x["id"] == rid for x in rewards2)


# ---------- Point shop tabs endpoints ----------
def test_points_ledger_shape():
    r = requests.get(f"{API}/points/ledger", cookies=viewer_cookies())
    assert r.status_code == 200
    assert "entries" in r.json()


def test_points_ledger_unauth():
    r = requests.get(f"{API}/points/ledger")
    assert r.status_code == 401


def test_points_redemptions_shape():
    r = requests.get(f"{API}/points/redemptions", cookies=viewer_cookies())
    assert r.status_code == 200
    assert "redemptions" in r.json()
    assert isinstance(r.json()["redemptions"], list)


def test_points_leaderboard_public():
    r = requests.get(f"{API}/points/leaderboard")
    assert r.status_code == 200
    d = r.json()
    assert "leaderboard" in d
    if d["leaderboard"]:
        row = d["leaderboard"][0]
        for k in ("rank", "username", "points"):
            assert k in row


# ---------- Admin cookie alone accesses admin endpoints ----------
def test_admin_cookie_can_list_users(admin_sess):
    r = admin_sess.get(f"{API}/admin/users")
    assert r.status_code == 200
    assert "users" in r.json()


def test_no_cookie_admin_endpoints_401_or_403():
    r = requests.get(f"{API}/admin/users")
    assert r.status_code in (401, 403)
    r2 = requests.post(f"{API}/admin/giveaways",
                       json={"title": "x", "description": "y", "prize": "z"})
    assert r2.status_code in (401, 403)
