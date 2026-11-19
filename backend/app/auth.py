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


def decode_token(token: str) -> Tenant:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    return Tenant(organization_id=payload["org"], user_id=payload["sub"])


async def get_tenant(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Tenant:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return decode_token(creds.credentials)


class SignupIn(BaseModel):
    organization_name: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _public_user(user: dict, org: dict | None) -> dict:
    return {
        "id": user["_id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "organization": {"id": user["organization_id"], "name": org["name"] if org else ""},
    }


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
    return {"token": issue_token(user["_id"], org["_id"]), "user": _public_user(user, org)}


@router.post("/login")
async def login(body: LoginIn):
    db = get_db()
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    org = await db.organizations.find_one({"_id": user["organization_id"]})
    return {"token": issue_token(user["_id"], user["organization_id"]), "user": _public_user(user, org)}


@router.get("/me")
async def me(tenant: Tenant = Depends(get_tenant)):
    db = get_db()
    user = await db.users.find_one({"_id": tenant.user_id, "organization_id": tenant.organization_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    org = await db.organizations.find_one({"_id": tenant.organization_id})
    return _public_user(user, org)
