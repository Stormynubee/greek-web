"""MongoDB models with PyObjectId + BaseDocument helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Optional
from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, BeforeValidator


def _validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError(f"Invalid ObjectId: {v!r}")


PyObjectId = Annotated[str, BeforeValidator(_validate_object_id)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: Optional[dict]):
        if not doc:
            return None
        data = dict(doc)
        if "_id" in data:
            data["_id"] = str(data["_id"])
        return cls(**data)

    def to_mongo(self, exclude_id: bool = True) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if exclude_id and "_id" in data:
            data.pop("_id")
        for k, v in list(data.items()):
            if isinstance(v, datetime):
                data[k] = v.isoformat()
        return data


class User(BaseDocument):
    discord_id: str
    username: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "viewer"
    points_balance: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class UserPublic(BaseModel):
    id: str
    discord_id: str
    username: str
    avatar_url: Optional[str] = None
    role: str
    points_balance: int


class LedgerEntry(BaseDocument):
    user_id: str
    delta: int
    balance_after: int
    reason: str
    idempotency_key: Optional[str] = None
    ref: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Reward(BaseDocument):
    title: str
    description: str
    cost: int
    stock: int
    image_url: Optional[str] = None
    active: bool = True
    category: str = "custom"  # custom | bonus | tip | vip
    requires: Optional[str] = None  # e.g. "Rainbet username"
    created_at: datetime = Field(default_factory=utcnow)


class StreamGame(BaseDocument):
    title: str
    kind: str
    status: str = "open"
    entry_cost: int = 0
    reward_pool: int = 0
    prompt: Optional[str] = None
    options: list[str] = Field(default_factory=list)
    winning_option: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: Optional[datetime] = None


class GameEntry(BaseDocument):
    game_id: str
    user_id: str
    choice: Optional[str] = None
    stake: int = 0
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Giveaway ----------
class Giveaway(BaseDocument):
    title: str
    description: str
    prize: str
    image_url: Optional[str] = None
    max_winners: int = 1
    status: str = "open"  # open | drawn | closed
    ends_at: Optional[datetime] = None
    winners: list[dict[str, str]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    drawn_at: Optional[datetime] = None


class GiveawayEntry(BaseDocument):
    giveaway_id: str
    user_id: str
    username: str
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Custom Leaderboard entries (admin can add manual) ----------
class CustomLeaderboardEntry(BaseDocument):
    display_name: str
    wagered: float
    bets: int = 0
    note: Optional[str] = None
    board: str = "monthly"  # daily | weekly | monthly
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Live status (LIVE on KICK widget) ----------
class LiveStatus(BaseDocument):
    is_live: bool = False
    platform: str = "kick"
    title: Optional[str] = None
    url: Optional[str] = "https://kick.com/greekgodberry"
    updated_at: datetime = Field(default_factory=utcnow)


# ---------- Admin (bcrypt password + brute force) ----------
class AdminAccount(BaseDocument):
    username: str
    password_hash: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
