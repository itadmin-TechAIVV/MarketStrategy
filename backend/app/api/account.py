"""The signed-in user's own account: profile, password and preferences."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import Tenant, get_tenant, hash_password, issue_token, public_user, verify_password
from ..db import get_db, utcnow
from ..services.account import AccountError, check_new_password, merge_preferences, preferences_of

router = APIRouter(prefix="/api/account", tags=["account"])


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    organization_name: str | None = Field(default=None, min_length=1, max_length=120)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class PreferencesIn(BaseModel):
    theme: str | None = None
    jack_autostart: bool | None = None


async def _load(tenant: Tenant) -> tuple[dict, dict | None]:
    db = get_db()
    user = await db.users.find_one({"_id": tenant.user_id, "organization_id": tenant.organization_id})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    org = await db.organizations.find_one({"_id": tenant.organization_id})
    return user, org


@router.patch("/profile")
async def update_profile(body: ProfileIn, tenant: Tenant = Depends(get_tenant)):
    db = get_db()
    user, org = await _load(tenant)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Your name can't be empty")
        await db.users.update_one({"_id": user["_id"]}, {"$set": {"name": name, "updated_at": utcnow()}})
    if body.organization_name is not None:
        if user["role"] != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can rename the organisation")
        org_name = body.organization_name.strip()
        if not org_name:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The organisation name can't be empty")
        await db.organizations.update_one({"_id": tenant.organization_id}, {"$set": {"name": org_name}})
    user, org = await _load(tenant)
    return public_user(user, org)


@router.post("/password")
async def change_password(body: PasswordIn, tenant: Tenant = Depends(get_tenant)):
    """Change the password and sign out every other session. Returns a fresh token for this one."""
    user, org = await _load(tenant)
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not correct")
    try:
        check_new_password(body.new_password, email=user["email"], current_password=body.current_password)
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    now = utcnow().replace(microsecond=0)
    await get_db().users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": hash_password(body.new_password), "password_changed_at": now, "tokens_valid_after": now}},
    )
    user, org = await _load(tenant)
    return {"token": issue_token(user["_id"], user["organization_id"]), "user": public_user(user, org)}


@router.patch("/preferences")
async def update_preferences(body: PreferencesIn, tenant: Tenant = Depends(get_tenant)):
    user, _ = await _load(tenant)
    try:
        prefs = merge_preferences(preferences_of(user), body.model_dump(exclude_none=True))
    except AccountError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"preferences": prefs}})
    return prefs
