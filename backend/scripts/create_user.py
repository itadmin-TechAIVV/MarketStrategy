"""Create users for the GTM Strategy Agent.

Easiest: run backend\\create_user.bat (or double-click it). It asks step by step:
email, name, organisation (new or existing), role and password.

Same thing from the backend/ folder:
    .\\.venv\\Scripts\\python -m scripts.create_user

Optional one-line forms, for scripting:
    .\\.venv\\Scripts\\python -m scripts.create_user add asha@acme.com --name "Asha Rao" --org "Acme Inc."
    .\\.venv\\Scripts\\python -m scripts.create_user add ravi@acme.com --org-id <organisation id> --role member
    .\\.venv\\Scripts\\python -m scripts.create_user list
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from email_validator import EmailNotValidError, validate_email
from pymongo.errors import DuplicateKeyError

from app import db
from app.auth import hash_password
from app.db import new_id, utcnow

MIN_PASSWORD = 8  # same rule as the signup form


class UserError(Exception):
    """A problem the person running the script can fix (shown without a traceback)."""


def clean_email(raw: str) -> str:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as e:
        raise UserError(f"Invalid email: {e}")


def ask_password() -> str:
    while True:
        pw = getpass.getpass(f"Password (min {MIN_PASSWORD} characters, hidden while typing): ")
        if len(pw) < MIN_PASSWORD:
            print(f"  Too short, use at least {MIN_PASSWORD} characters.")
            continue
        if getpass.getpass("Repeat password: ") != pw:
            print("  Passwords didn't match, try again.")
            continue
        return pw


async def get_orgs() -> list[dict]:
    database = db.get_db()
    orgs = [o async for o in database.organizations.find({}, {"name": 1}).sort("created_at", 1)]
    for o in orgs:
        o["user_count"] = await database.users.count_documents({"organization_id": o["_id"]})
    return orgs


async def create_user(email: str, name: str, password: str, role: str, org_id: str | None, org_name: str | None) -> dict:
    """Create the user, plus a new organisation when org_id is None. Returns the organisation."""
    if len(password) < MIN_PASSWORD:
        raise UserError(f"Password must be at least {MIN_PASSWORD} characters.")
    database = db.get_db()
    await db.ensure_indexes()

    if await database.users.find_one({"email": email}):
        raise UserError(f"A user with email {email} already exists.")

    new_org = None
    if org_id:
        org = await database.organizations.find_one({"_id": org_id})
        if not org:
            raise UserError(f"No organisation with id {org_id}.")
    else:
        new_org = org = {"_id": new_id(), "name": org_name or f"{name}'s organisation", "created_at": utcnow()}

    user = {
        "_id": new_id(),
        "organization_id": org["_id"],
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "created_at": utcnow(),
    }
    try:
        await database.users.insert_one(user)
    except DuplicateKeyError:
        raise UserError(f"A user with email {email} already exists.")
    if new_org:
        await database.organizations.insert_one(new_org)
    return org


# ---------------------------------------------------------------- interactive

def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("  This is required.")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        value = input(f"{prompt} ({hint}): ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("  Please type y or n.")


async def interactive() -> None:
    print("\n=== Create a user for GTM Strategy Agent ===")
    print("Press Ctrl+C at any time to cancel.\n")
    database = db.get_db()

    while True:
        # 1. Email
        while True:
            try:
                email = clean_email(ask("1. Email"))
            except UserError as e:
                print(f"  {e}")
                continue
            if await database.users.find_one({"email": email}):
                print(f"  A user with {email} already exists. Use a different email.")
                continue
            break

        # 2. Name
        name = ask("2. Full name", default=email.split("@")[0])

        # 3. Organisation
        orgs = await get_orgs()
        org_id, org_name = None, None
        print("\n3. Organisation (users in the same organisation share strategies)")
        print("   0) Create a new organisation")
        for i, o in enumerate(orgs, 1):
            print(f"   {i}) {o['name']}  ({o['user_count']} user{'s' if o['user_count'] != 1 else ''})")
        while True:
            choice = ask("   Choose a number", default="0")
            if choice.isdigit() and 0 <= int(choice) <= len(orgs):
                break
            print(f"  Type a number from 0 to {len(orgs)}.")
        if choice == "0":
            org_name = ask("   New organisation name")
        else:
            picked = orgs[int(choice) - 1]
            org_id, org_name = picked["_id"], picked["name"]

        # 4. Role
        default_role = "admin" if org_id is None else "member"
        while True:
            role = ask("\n4. Role (admin or member)", default=default_role).lower()
            if role in ("admin", "member"):
                break
            print("  Type admin or member.")

        # 5. Password
        print()
        password = ask_password()

        # Confirm
        print("\n--- Check the details ---")
        print(f"Email:        {email}")
        print(f"Name:         {name}")
        print(f"Organisation: {org_name}{'  (new)' if org_id is None else ''}")
        print(f"Role:         {role}")
        if ask_yes_no("\nCreate this user?"):
            try:
                await create_user(email, name, password, role, org_id, org_name)
                print(f"\nDone. {email} can now log in with this password.")
            except UserError as e:
                print(f"\nNot created: {e}")
        else:
            print("Cancelled, nothing was saved.")

        if not ask_yes_no("\nCreate another user?", default=False):
            break
        print()


# ---------------------------------------------------------------- one-line commands

async def cmd_add(args: argparse.Namespace) -> None:
    email = clean_email(args.email)
    password = args.password if args.password is not None else ask_password()
    name = args.name or email.split("@")[0]
    org = await create_user(email, name, password, args.role, args.org_id, args.org)
    print(f"Created user {email} ({args.role}) in organisation '{org['name']}' (id {org['_id']}).")


async def cmd_list(_: argparse.Namespace) -> None:
    database = db.get_db()
    orgs = await get_orgs()
    if not orgs:
        print("No users yet.")
        return
    for o in orgs:
        print(f"\n{o['name']}  [org id {o['_id']}]")
        async for u in database.users.find({"organization_id": o["_id"]}).sort("created_at", 1):
            print(f"  - {u['email']:<36} {u.get('name', ''):<24} {u.get('role', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.create_user", description="Create or list users. Run with no arguments to be asked step by step.")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="create a user in one line")
    p_add.add_argument("email")
    p_add.add_argument("--name", help="display name (default: part of the email before @)")
    group = p_add.add_mutually_exclusive_group()
    group.add_argument("--org", help="name for a NEW organisation")
    group.add_argument("--org-id", help="add the user to this EXISTING organisation (see 'list')")
    p_add.add_argument("--role", choices=["admin", "member"], default="admin")
    p_add.add_argument("--password", help="skip the prompt (visible in shell history)")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="list organisations and users")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()

    async def run() -> None:
        try:
            if args.command is None:
                await interactive()
            else:
                await args.func(args)
        finally:
            await db.close()

    try:
        asyncio.run(run())
    except UserError as e:
        sys.exit(str(e))
    except (KeyboardInterrupt, EOFError):
        sys.exit("\nCancelled, nothing was saved.")


if __name__ == "__main__":
    main()
