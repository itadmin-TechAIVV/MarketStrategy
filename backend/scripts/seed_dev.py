"""Create a dev organisation and user for local testing.

Usage (from backend/):  python -m scripts.seed_dev you@example.com "a-long-password"
The credentials are whatever you pass; nothing is hard-coded.
"""
import asyncio
import sys

from app import db
from app.auth import create_org_and_user


async def main(email: str, password: str) -> None:
    await db.ensure_indexes()
    org, user = await create_org_and_user("Dev Organisation", "Dev User", email, password)
    print(f"Created organisation {org['_id']} and user {user['email']}")
    await db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit('usage: python -m scripts.seed_dev <email> "<password (8+ chars)>"')
    asyncio.run(main(sys.argv[1], sys.argv[2]))
