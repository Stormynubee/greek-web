"""Contract tests for the internal points automation endpoints.

These run without MongoDB — they verify request validation, secret
handling, and the pure logic around the new chat-award route using
fakes for the database layer.
"""
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

# Set env BEFORE importing server so module-level flags are correct.
for k, v in {
    "APP_ENV": "test",
    "MONGO_URL": "mongodb://localhost:27017/greekgodberry",
    "DB_NAME": "greekgodberry",
    "DISCORD_CLIENT_ID": "test-client-id",
    "DISCORD_CLIENT_SECRET": "test-client-secret",
    "DISCORD_REDIRECT_URI": "http://localhost:8000/api/auth/discord/callback",
    "FRONTEND_URL": "http://localhost:3000",
    "LOCKLY_API_BASE": "https://public-api.lockly.io/api/public/streamer",
    "LOCKLY_API_KEY": "test-lockly-key",
    "JWT_SECRET": "user-session-secret-for-tests",
    "ADMIN_JWT_SECRET": "admin-session-secret-for-tests",
    "OWNER_EMAIL": "owner@example.com",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "test-admin-password",
    "INTERNAL_POINTS_SECRET": "test-internal-secret",
    "CHAT_POINTS_ENABLED": "true",
    "WATCH_POINTS_ENABLED": "true",
    "WATCH_POINTS_DAILY_CAP": "360",
}.items():
    os.environ.setdefault(k, v)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def _matches(self, doc, query):
        for k, v in query.items():
            if isinstance(v, dict) and "$gte" in v:
                if doc.get(k, 0) < v["$gte"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, query, *args, **kwargs):
        for d in self.docs:
            if self._matches(d, query):
                return d
        return None

    async def count_documents(self, query, **kwargs):
        return sum(1 for d in self.docs if self._matches(d, query))


def _make_request(secret="test-internal-secret"):
    return SimpleNamespace(headers={"x-internal-secret": secret})


def _body(**overrides):
    defaults = dict(discord_id="123456789", source="kick",
                    platform_username="u", event_id="abcd1234")
    defaults.update(overrides)
    return server.ChatAwardBody(**defaults)


# ---------- secret handling ----------

@pytest.mark.asyncio
async def test_chat_award_rejects_missing_secret():
    with pytest.raises(HTTPException) as exc:
        await server.internal_chat_award(_make_request(""), _body())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_chat_award_rejects_wrong_secret():
    with pytest.raises(HTTPException) as exc:
        await server.internal_chat_award(_make_request("wrong"), _body())
    assert exc.value.status_code == 401


# ---------- body validation ----------

@pytest.mark.asyncio
async def test_chat_award_rejects_bad_source():
    with pytest.raises(HTTPException) as exc:
        await server.internal_chat_award(_make_request(), _body(source="youtube"))
    assert exc.value.status_code == 422


def test_chat_award_rejects_short_event_id():
    with pytest.raises(Exception):
        _body(event_id="ab")


# ---------- award flow with fake db ----------

def _fake_user_doc(discord_id="123456789"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return {
        "discord_id": discord_id, "username": "testuser", "points_balance": 5,
        "role": "viewer", "created_at": now, "updated_at": now,
    }


@pytest.mark.asyncio
async def test_chat_award_no_account_skips():
    server.db = SimpleNamespace(users=_FakeCollection(), ledger=_FakeCollection())
    result = await server.internal_chat_award(_make_request(), _body(discord_id="unknown-user"))
    assert result == {"awarded": False, "reason": "no_account"}


@pytest.mark.asyncio
async def test_chat_award_cooldown_skip():
    now = time.time()
    server.db = SimpleNamespace(
        users=_FakeCollection([_fake_user_doc()]),
        ledger=_FakeCollection([
            {"user_id": "123456789", "reason": "chat_kick", "ts": now - 60},  # 60s ago < 180s
        ]),
    )
    result = await server.internal_chat_award(_make_request(), _body())
    assert result == {"awarded": False, "reason": "cooldown"}


@pytest.mark.asyncio
async def test_chat_award_disabled(monkeypatch):
    monkeypatch.setattr(server, "CHAT_POINTS_ENABLED", False)
    server.db = SimpleNamespace(users=_FakeCollection(), ledger=_FakeCollection())
    result = await server.internal_chat_award(_make_request(), _body())
    assert result == {"awarded": False, "reason": "disabled"}


@pytest.mark.asyncio
async def test_chat_award_per_source_cooldown_independence():
    """A Kick message 60s ago must NOT block a Twitch award — per-source cooldown."""
    now = time.time()
    server.db = SimpleNamespace(
        users=_FakeCollection([_fake_user_doc()]),
        ledger=_FakeCollection([
            {"user_id": "123456789", "reason": "chat_kick", "ts": now - 60},
        ]),
    )
    # The cooldown gate must pass (no chat_twitch entry exists). The call will
    # proceed into _apply_ledger which needs a real txn — any exception raised
    # there must NOT be a cooldown response.
    with pytest.raises(Exception) as exc:
        await server.internal_chat_award(_make_request(), _body(source="twitch"))
    detail = str(getattr(exc.value, "detail", "") or exc.value)
    assert "cooldown" not in detail.lower()
