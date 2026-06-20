"""Apply a SQL migration file to DATABASE_URL.

Usage:
    .venv/bin/python -m scripts.apply_migration db/migrations/001_xxx.sql
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

from db.connection import engine


async def main(path: str) -> None:
    if not engine:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)
    sql = Path(path).read_text()
    # asyncpg can't run multi-statement scripts in a single execute, so split.
    # Naive splitter: respects DO $$ … $$ blocks by tracking dollar-quote state.
    stmts = _split_sql(sql)
    async with engine.begin() as conn:
        for i, stmt in enumerate(stmts, 1):
            s = stmt.strip()
            if not s:
                continue
            print(f"[{i}/{len(stmts)}] {s[:80].splitlines()[0]}…")
            await conn.exec_driver_sql(s)
    print("migration applied OK")


def _split_sql(sql: str) -> list[str]:
    """Split on `;` at statement level, ignoring `;` inside `$$ … $$`."""
    out: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if sql[i:i + 2] == "$$":
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        if ch == ";" and not in_dollar:
            out.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: apply_migration <path-to-sql>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(sys.argv[1]))
