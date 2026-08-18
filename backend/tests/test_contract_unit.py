"""Pure contract tests that do not require MongoDB or external services."""
import asyncio
import importlib
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError


SERVER_ENV = {
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
}


@pytest.fixture
def server_module(monkeypatch):
    monkeypatch.setenv("APP_ENV", SERVER_ENV["APP_ENV"])
    for name, value in SERVER_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    sys.modules.pop("server", None)
    return importlib.import_module("server")


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *args):
        return self

    def limit(self, *args):
        return self

    async def to_list(self, *args):
        return self.rows


class _CustomLeaderboard:
    def find(self, *args):
        return _Cursor([
            {"display_name": "HouseEntry", "wagered": 50, "bets": 2},
        ])


class _Database:
    custom_leaderboard = _CustomLeaderboard()


class _EmptyCustomLeaderboard:
    def find(self, *args):
        return _Cursor([])


class _EmptyDatabase:
    custom_leaderboard = _EmptyCustomLeaderboard()


class _Response:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class _HttpClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class _AsyncEntries:
    def __init__(self, entries):
        self.entries = entries

    def __aiter__(self):
        async def generate():
            for entry in self.entries:
                yield entry

        return generate()


def test_leaderboard_preserves_upstream_totals_when_rows_are_capped(server_module, monkeypatch):
    async def fake_fetch(_kind):
        return {
            "success": True,
            "responseObject": {
                "type": "monthly",
                "from": "2026-08-01T00:00:00.000Z",
                "totalUsers": 14,
                "totalWagered": 1333.11,
                "rankings": [
                    {
                        "user": {"name": "TopPlayer"},
                        "wagerAmount": 100,
                        "betCount": 5,
                    },
                ],
            },
        }

    monkeypatch.setattr(server_module, "_fetch_lockly", fake_fetch)
    monkeypatch.setattr(server_module, "db", _Database())

    result = asyncio.run(server_module.leaderboard(type="monthly"))

    assert result["total_users"] == 15
    assert result["total_wagered"] == 1383.11
    assert result["rankings"][0]["name"] == "TopPlayer"
    assert result["source_status"] == "lockly"
    assert result["upstream_unavailable"] is False


def test_leaderboard_does_not_relabel_stale_lockly_rows_as_current(server_module, monkeypatch):
    async def unavailable(_kind):
        return {
            "responseObject": {
                "type": "monthly",
                "rankings": [],
                "totalUsers": 14,
                "totalWagered": 1333.11,
            },
            "upstream_unavailable": True,
        }

    monkeypatch.setattr(server_module, "_fetch_lockly", unavailable)
    monkeypatch.setattr(server_module, "db", _EmptyDatabase())

    result = asyncio.run(server_module.leaderboard(type="monthly"))

    assert result["rankings"] == []
    assert result["total_users"] == 0
    assert result["total_wagered"] == 0
    assert result["source_status"] == "unavailable"


def test_leaderboard_skips_malformed_lockly_rows(server_module, monkeypatch):
    async def malformed(_kind):
        return {
            "responseObject": {
                "type": "weekly",
                "rankings": [
                    {"user": {}, "wagerAmount": 100, "betCount": 2},
                    {"user": {"name": "Negative"}, "wagerAmount": -1, "betCount": 2},
                    {"user": {"name": "Valid"}, "wagerAmount": 10, "betCount": 1},
                ],
                "totalUsers": 3,
                "totalWagered": 10,
            },
        }

    monkeypatch.setattr(server_module, "_fetch_lockly", malformed)
    monkeypatch.setattr(server_module, "db", _EmptyDatabase())

    result = asyncio.run(server_module.leaderboard(type="weekly"))

    assert [row["name"] for row in result["rankings"]] == ["Valid"]
    assert result["source_status"] == "lockly"


def test_cerberus_bridge_requires_config_and_marks_unavailable(server_module):
    server_module._cerberus_live_cache = None
    result = asyncio.run(server_module._fetch_cerberus_live_state())

    assert result["available"] is False
    assert result["stale"] is False
    assert result["error"] == "not_configured"


def test_reference_bingo_payload_is_sanitized(server_module):
    safe = server_module._sanitize_bingo_game({
        "id": "game-1",
        "title": "Bonus Bingo",
        "status": "ACTIVE",
        "cells": [{
            "id": "cell-1",
            "row": 0,
            "col": 0,
            "status": "GREEN",
            "claimedByChatUsername": "viewer",
            "claimedByUserId": "private-user-id",
            "claimedBy": {"id": "private-user-id"},
        }],
        "participants": [{
            "id": "participant-1",
            "chatUsername": "viewer",
            "userId": "private-user-id",
            "user": {"id": "private-user-id"},
        }],
        "lineWins": [],
    })

    assert safe["cells"][0]["claimedByChatUsername"] == "viewer"
    assert "claimedByUserId" not in safe["cells"][0]
    assert "userId" not in safe["participants"][0]
    assert "user" not in safe["participants"][0]


def test_game_create_rejects_negative_money_values(server_module):
    with pytest.raises(ValidationError):
        server_module.GameCreate(
            title="Invalid",
            kind="prediction",
            entry_cost=-1,
        )

    with pytest.raises(ValidationError):
        server_module.GameCreate(
            title="Invalid",
            kind="prediction",
            reward_pool=-1,
        )


def test_giveaway_create_requires_a_positive_winner_count(server_module):
    with pytest.raises(ValidationError):
        server_module.GiveawayCreate(
            title="Invalid",
            description="",
            prize="Nothing",
            max_winners=0,
        )


def test_retry_after_parser_supports_seconds_and_http_dates(server_module):
    assert server_module._retry_after_seconds("7", now=100) == 7
    assert server_module._retry_after_seconds("not-a-date", now=100) is None


def test_lockly_request_uses_documented_path_header_and_limit(server_module, monkeypatch):
    response = _Response(
        200,
        {
            "success": True,
            "responseObject": {"rankings": [], "totalUsers": 0, "totalWagered": 0},
        },
    )
    client = _HttpClient(response)
    monkeypatch.setattr(server_module, "_get_http_client", lambda: asyncio.sleep(0, result=client))
    server_module._lockly_cache.clear()
    server_module._lockly_retry_at.clear()

    asyncio.run(server_module._fetch_lockly("weekly"))

    url, kwargs = client.calls[0]
    assert url == f"{server_module.LOCKLY_STREAMER_BASE}/leaderboard"
    assert kwargs["params"] == {"type": "weekly", "limit": server_module.LOCKLY_LIMIT}
    assert kwargs["headers"] == {"x-streamer-api-key": server_module.LOCKLY_API_KEY}


class _OAuthStates:
    def __init__(self):
        self.document = None

    async def insert_one(self, document):
        self.document = document


class _OAuthDatabase:
    def __init__(self):
        self.oauth_states = _OAuthStates()


def test_discord_login_stores_state_server_side_without_cookie(server_module, monkeypatch):
    from fastapi import Response

    database = _OAuthDatabase()
    monkeypatch.setattr(server_module, "db", database)
    response = Response()
    asyncio.run(server_module.discord_login(response))

    assert "set-cookie" not in response.headers
    assert database.oauth_states.document["state_hash"]
    assert database.oauth_states.document["expires_at"] > server_module.utcnow()


def test_oauth_failure_reason_is_safe_and_specific(server_module):
    assert server_module._oauth_failure_reason(error="access_denied") == "oauth_denied"
    assert server_module._oauth_failure_reason(state="bad") == "state_invalid"
    assert server_module._oauth_failure_reason(token_status=401) == "token_exchange"
    assert server_module._oauth_failure_reason(profile_status=500) == "discord_profile"


def test_oauth_failure_redirect_contains_reason_without_upstream_details(server_module):
    response = server_module._oauth_error_response("token_exchange")
    query = parse_qs(urlparse(response.headers["location"]).query)

    assert query["auth"] == ["error"]
    assert query["reason"] == ["token_exchange"]
    assert "client_secret" not in response.headers["location"]


def test_lockly_rate_limit_serves_stale_data_and_collapses_retries(server_module, monkeypatch):
    stale = {
        "success": True,
        "responseObject": {"rankings": [], "totalUsers": 2, "totalWagered": 10},
    }
    response = _Response(429, {"success": False}, {"retry-after": "60"})
    client = _HttpClient(response)
    monkeypatch.setattr(server_module, "_get_http_client", lambda: asyncio.sleep(0, result=client))
    server_module._lockly_cache["daily"] = (0, stale)
    server_module._lockly_retry_at.clear()

    result = asyncio.run(server_module._fetch_lockly("daily"))
    retry_result = asyncio.run(server_module._fetch_lockly("daily"))

    assert result["upstream_unavailable"] is True
    assert retry_result["upstream_unavailable"] is True
    assert client.calls == [
        (
            f"{server_module.LOCKLY_STREAMER_BASE}/leaderboard",
            {
                "params": {"type": "daily", "limit": server_module.LOCKLY_LIMIT},
                "headers": {"x-streamer-api-key": server_module.LOCKLY_API_KEY},
            },
        )
    ]


def test_secure_sample_uses_bounded_reservoir(server_module, monkeypatch):
    calls = []

    def randbelow(upper):
        calls.append(upper)
        return 0

    monkeypatch.setattr(server_module.secrets, "randbelow", randbelow)
    result = asyncio.run(server_module._secure_sample_entries(
        _AsyncEntries([{"user_id": "a"}, {"user_id": "b"}, {"user_id": "c"}]),
        2,
    ))

    assert len(result) == 2
    assert calls == [3]


def test_production_configuration_rejects_placeholder_values(server_module, monkeypatch):
    monkeypatch.setattr(server_module, "APP_ENV", "production")
    monkeypatch.setattr(server_module, "DISCORD_CLIENT_SECRET", "replace-with-discord-secret")

    with pytest.raises(RuntimeError, match="Rotate"):
        server_module._validate_production_configuration()
