# Tencent is pleased to support the open source community by making tRPC-Agent-Python available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Agent-Python is licensed under Apache-2.0.
"""Database initialization script for the code review agent.

Usage:
    python init_db.py [--db-path path/to/review.db]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def init_db(db_path: str) -> None:
    """Initialize the database by executing schema.sql."""
    schema_path = Path(__file__).parent / "db" / "schema.sql"
    if not schema_path.exists():
        print(f"Error: schema.sql not found at {schema_path}", file=sys.stderr)
        sys.exit(1)

    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3

    conn = sqlite3.connect(str(db_file))
    try:
        conn.executescript(schema_path.read_text())
        conn.commit()
        print(f"✅ Database initialized at {db_file.resolve()}")
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize code review database")
    parser.add_argument(
        "--db-path",
        default="review.db",
        help="Path to the SQLite database file (default: review.db)",
    )
    args = parser.parse_args()
    init_db(args.db_path)


if __name__ == "__main__":
    main()