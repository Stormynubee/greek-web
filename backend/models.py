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
        # datetimes stored as ISO strings — leave them (pydantic will parse)
        return cls(**data)

    def to_mongo(self, exclude_id: bool = True) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        if exclude_id and "_id" in data:
            data.pop("_id")
        # convert datetime → ISO string
        for k, v in list(data.items()):
            if isinstance(v, datetime):
                data[k] = v.isoformat()
        return data


# ---------- User ----------
class User(BaseDocument):
    discord_id: str
    username: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str = "viewer"  # "viewer" | "owner"
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


# ---------- Points Ledger (append-only) ----------
class LedgerEntry(BaseDocument):
    user_id: str
    delta: int  # positive = credit, negative = debit
    balance_after: int
    reason: str  # "signup_bonus" | "game_reward" | "store_redeem" | "admin_grant"
    idempotency_key: Optional[str] = None
    ref: Optional[str] = None  # e.g., reward_id or game_id
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Store Reward ----------
class Reward(BaseDocument):
    title: str
    description: str
    cost: int
    stock: int  # -1 = unlimited
    image_url: Optional[str] = None
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Stream Game ----------
class StreamGame(BaseDocument):
    title: str
    kind: str  # "prediction" | "quiz" | "raffle"
    status: str = "open"  # "open" | "closed" | "resolved"
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
