"""Login, signup and the tenant context dependency.

All token handling lives in this module, so swapping to Grow CRM's login later
only means replacing `decode_token` / `get_tenant`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError

from .config import get_settings
from .db import get_db, new_id, utcnow
from .services.account import onboarding_state, preferences_of

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Tenant:
    organization_id: str
    user_id: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def issue_token(user_id: str, organization_id: str) -> str:
    s = get_settings()
    now = utcnow()
    payload = {"sub": user_id, "org": organization_id, "iat": now, "exp": now + timedelta(hours=s.jwt_expiry_hours)}
    return jwt.encode(payload, s.jwt_secret.get_secret_value(), algorithm="HS256")


def _payload(token: str) -> dict:
    try:
        return jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")


def decode_token(token: str) -> Tenant:
    payload = _payload(token)
    return Tenant(organization_id=payload["org"], user_id=payload["sub"])


def session_revoked(issued_at: int, user: dict) -> bool:
    """True when the token predates the user's last password change (other sessions are signed out)."""
    valid_after = user.get("tokens_valid_after")
    return bool(valid_after) and issued_at < int(valid_after.timestamp())


async def get_tenant(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Tenant:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    payload = _payload(creds.credentials)
    tenant = Tenant(organization_id=payload["org"], user_id=payload["sub"])
    user = await get_db().users.find_one(
        {"_id": tenant.user_id, "organization_id": tenant.organization_id}, {"tokens_valid_after": 1}
    )
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    if session_revoked(int(payload.get("iat", 0)), user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your password was changed. Please log in again.")
    return tenant


class SignupIn(BaseModel):
    organization_name: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def public_user(user: dict, org: dict | None) -> dict:
    return {
        "id": user["_id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "organization": {"id": user["organization_id"], "name": org["name"] if org else ""},
        "created_at": user.get("created_at"),
        "first_login_at": user.get("first_login_at"),
        "password_changed_at": user.get("password_changed_at"),
        "preferences": preferences_of(user),
        "onboarding": onboarding_state(user.get("first_login_at"), utcnow()),
    }


async def record_login(user: dict) -> dict:
    """Stamp last_login_at, and first_login_at the very first time (it starts Jack's onboarding window)."""
    now = utcnow()
    changes: dict = {"last_login_at": now}
    if not user.get("first_login_at"):
        changes["first_login_at"] = now
    await get_db().users.update_one({"_id": user["_id"]}, {"$set": changes})
    return {**user, **changes}


async def create_org_and_user(organization_name: str, name: str, email: str, password: str) -> tuple[dict, dict]:
    db = get_db()
    org = {"_id": new_id(), "name": organization_name, "created_at": utcnow()}
    user = {
        "_id": new_id(),
        "organization_id": org["_id"],
        "name": name,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "role": "admin",
        "created_at": utcnow(),
    }
    try:
        await db.users.insert_one(user)
    except DuplicateKeyError:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    await db.organizations.insert_one(org)
    return org, user


@router.post("/signup")
async def signup(body: SignupIn):
    org, user = await create_org_and_user(body.organization_name, body.name, body.email, body.password)
    user = await record_login(user)
    return {"token": issue_token(user["_id"], org["_id"]), "user": public_user(user, org)}


@router.post("/login")
async def login(body: LoginIn):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    user = await record_login(user)
    org = await db.organizations.find_one({"_id": user["organization_id"]})
    return {"token": issue_token(user["_id"], user["organization_id"]), "user": public_user(user, org)}


@router.get("/me")
async def me(tenant: Tenant = Depends(get_tenant)):
    db = get_db()
    user = await db.users.find_one({"_id": tenant.user_id, "organization_id": tenant.organization_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    if not user.get("first_login_at"):
        # Accounts that were already signed in before onboarding existed start their window now.
        user = await record_login(user)
    org = await db.organizations.find_one({"_id": tenant.organization_id})
    return public_user(user, org)
