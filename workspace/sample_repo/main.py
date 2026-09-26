"""
sample_repo/main.py – Minimal FastAPI app used as a test fixture for ast_parser.
"""

from __future__ import annotations

import re
from typing import List, Optional

from fastapi import FastAPI, APIRouter
from pydantic import BaseModel, field_validator

app = FastAPI(title="Sample App")
router = APIRouter(prefix="/users")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserBase(BaseModel):
    """Base user schema."""
    name: str
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid email address: {v!r}")
        return v


class UserCreate(UserBase):
    """Schema used when creating a new user."""
    password: str


class UserResponse(UserBase):
    """Schema returned from the API."""
    id: int
    active: bool = True


class ItemSchema(BaseModel):
    """A simple item schema."""
    title: str
    description: Optional[str] = None
    price: float


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

class UserService:
    """Business-logic layer for users."""

    def get_user(self, user_id: int) -> Optional[UserResponse]:
        """Fetch a user by ID."""
        return None

    def create_user(self, payload: UserCreate) -> UserResponse:
        """Persist a new user and return the created record."""
        return UserResponse(id=1, name=payload.name, email=payload.email)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

user_service = UserService()


@app.get("/health")
def health_check() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int) -> UserResponse:
    """Return a single user by ID."""
    result = user_service.get_user(user_id)
    if result is None:
        raise ValueError("not found")
    return result


@router.post("/", response_model=UserResponse)
def create_user(payload: UserCreate) -> UserResponse:
    """Create a new user."""
    return user_service.create_user(payload)


@router.delete("/{user_id}")
async def delete_user(user_id: int) -> dict:
    """Delete a user by ID."""
    return {"deleted": user_id}


@app.get("/items/")
def list_items() -> List[ItemSchema]:
    """Return all items."""
    return []


@app.post("/items/")
def create_item(payload: ItemSchema) -> ItemSchema:
    """Create a new item."""
    return payload


app.include_router(router)
