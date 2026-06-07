"""
capacity_forecast_db connection verifier.
Run from project root:  python check_db.py
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "capacity_forecast.db"

REQUIRED_TABLES = {"users", "settings", "sessions", "history", "metrics"}


def sep(char="-", width=55):
    print(char * width)


def main():
    sep("=")
    print("  Capacity Forecast -- SQLite Connection Check")
    sep("=")
    print(f"  DB path : {DB_PATH}")
    print(f"  Exists  : {DB_PATH.exists()}")
    sep()

    if not DB_PATH.exists():
        print("[FAIL] Database file not found.")
        print("       Start the backend once to auto-create it:")
        print("       cd backend && uvicorn app:app --reload")
        sys.exit(1)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row

        # Enable WAL + foreign keys (same as app.py)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        # ── Integrity check ──────────────────────────────────────
        cursor.execute("PRAGMA integrity_check")
        ic = cursor.fetchone()[0]
        status = "OK" if ic == "ok" else f"WARN ({ic})"
        print(f"  Integrity check   : {status}")

        # ── Foreign keys ─────────────────────────────────────────
        cursor.execute("PRAGMA foreign_keys")
        fk = cursor.fetchone()[0]
        print(f"  Foreign keys      : {'ON' if fk else 'OFF'}")

        # ── WAL journal mode ──────────────────────────────────────
        cursor.execute("PRAGMA journal_mode")
        jm = cursor.fetchone()[0]
        print(f"  Journal mode      : {jm.upper()}")

        sep()

        # ── Tables ────────────────────────────────────────────────
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        found_tables = {row[0] for row in cursor.fetchall()}
        missing = REQUIRED_TABLES - found_tables
        extra   = found_tables - REQUIRED_TABLES

        print(f"  Tables found ({len(found_tables)}):")
        for t in sorted(found_tables):
            cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
            count = cursor.fetchone()[0]
            marker = "[OK]" if t in REQUIRED_TABLES else "[?] "
            print(f"    {marker}  {t:<22} {count:>6} rows")

        if missing:
            print(f"\n  [WARN] Missing tables: {missing}")
        if extra:
            print(f"  [INFO] Extra tables : {extra}")

        sep()

        # ── Session health ────────────────────────────────────────
        now = datetime.now().isoformat()
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE expires_at < ?", (now,)
        )
        expired = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM sessions WHERE expires_at >= ?", (now,)
        )
        active = cursor.fetchone()[0]
        print(f"  Sessions active   : {active}")
        print(f"  Sessions expired  : {expired}  (cleaned automatically on next login)")

        # ── Users ─────────────────────────────────────────────────
        cursor.execute("SELECT email, name FROM users")
        users = cursor.fetchall()
        print(f"\n  Users ({len(users)}):")
        for u in users:
            print(f"    - {u['email']}  ({u['name']})")

        # ── Metrics sample ────────────────────────────────────────
        cursor.execute("SELECT MIN(date), MAX(date) FROM metrics")
        row = cursor.fetchone()
        if row[0]:
            print(f"\n  Metrics date range: {row[0]} to {row[1]}")

        conn.close()

        sep("=")
        if ic == "ok" and not missing:
            print("  [SUCCESS] SQLite database is connected and healthy!")
        else:
            print("  [WARN]    SQLite connected but has warnings -- review above.")
        sep("=")

    except sqlite3.DatabaseError as exc:
        sep("=")
        print(f"  [DATABASE ERROR] {exc}")
        sep("=")
        sys.exit(1)
    except Exception as exc:
        sep("=")
        print(f"  [UNEXPECTED ERROR] {exc}")
        import traceback
        traceback.print_exc()
        sep("=")
        sys.exit(1)


if __name__ == "__main__":
    main()
