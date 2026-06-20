"""
scripts/create_admin.py — bcrypt a password and print the JSON line for
ADMIN_USERS_JSON.

Usage:
    python -m scripts.create_admin alice@zerotoprod.tech "Alice" mypassword
    python -m scripts.create_admin alice@zerotoprod.tech "Alice"   # prompts for password

Append the printed dict to your existing ADMIN_USERS_JSON array, or use it
verbatim if you only need one admin. The app's lifespan hook reads
ADMIN_USERS_JSON on every boot and upserts each row into admin_users.
"""

from __future__ import annotations

import getpass
import json
import sys

from passlib.context import CryptContext


def main(argv: list[str]) -> int:
    if len(argv) < 3 or len(argv) > 4:
        print("Usage: python -m scripts.create_admin <email> <name> [password]", file=sys.stderr)
        return 2

    email = argv[1]
    name = argv[2]
    password = argv[3] if len(argv) == 4 else getpass.getpass("password: ")
    if not password:
        print("ERROR: password cannot be empty", file=sys.stderr)
        return 2

    ctx = CryptContext(schemes=["bcrypt"])
    record = {"email": email, "name": name, "password_hash": ctx.hash(password)}

    print()
    print("Add this to ADMIN_USERS_JSON in your .env (the value is a JSON array):")
    print()
    print(json.dumps([record], indent=2))
    print()
    print("Or as a single line:")
    print(json.dumps([record]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
