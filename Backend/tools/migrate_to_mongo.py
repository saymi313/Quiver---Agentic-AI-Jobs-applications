"""
Copy the local SQLite agent database into MongoDB.

Run once after pointing MONGODB_URI at a cluster, from Backend/:

    python tools/migrate_to_mongo.py            # copy everything
    python tools/migrate_to_mongo.py --dry-run  # report only, write nothing
    python tools/migrate_to_mongo.py --wipe     # clear the Mongo collections first

Ids are preserved, so foreign keys (job.company_id, outreach.person_id) keep
pointing at the right rows. Re-running is safe: companies, jobs and people are
matched on their natural keys and updated rather than duplicated.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import mongo_store, sqlite_store  # noqa: E402

COLLECTIONS = ("companies", "jobs", "people", "applications", "outreach", "runs", "settings")


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
    except sqlite3.OperationalError:
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy the SQLite agent DB into MongoDB")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wipe", action="store_true",
                    help="delete existing Mongo documents before copying")
    args = ap.parse_args()

    src = sqlite_store.DB_PATH
    if not src.is_file():
        print(f"[skip] no SQLite database at {src.name} — nothing to migrate.")
        return 0

    ok, reason = mongo_store.available()
    if not ok:
        print(f"[error] MongoDB is not reachable: {reason}", file=sys.stderr)
        return 1
    print(f"[ok] {reason}")

    conn = sqlite3.connect(str(src))
    conn.row_factory = sqlite3.Row

    tables = {
        "companies": _rows(conn, "companies"),
        "jobs": _rows(conn, "jobs"),
        "people": _rows(conn, "people"),
        "applications": _rows(conn, "applications"),
        "outreach": _rows(conn, "outreach"),
        "runs": _rows(conn, "runs"),
        "settings": _rows(conn, "settings"),
    }
    print("\nsource (SQLite):")
    for name, rows in tables.items():
        print(f"   {name:<14} {len(rows):>5}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    db = mongo_store._connect()
    if args.wipe:
        for name in COLLECTIONS:
            db[name].delete_many({})
        db.counters.delete_many({})
        print("\n[wipe] Mongo collections cleared.")

    print("\nwriting to MongoDB:")
    written = {}

    # Settings use the key as _id, not a sequence.
    for row in tables["settings"]:
        db.settings.update_one({"_id": row["key"]},
                               {"$set": {"value": row["value"],
                                         "updated_at": row.get("updated_at")}},
                               upsert=True)
    written["settings"] = len(tables["settings"])

    natural_key = {
        "companies": lambda r: {"name": r["name"], "source": r["source"]},
        "jobs": lambda r: {"url": r["url"]},
        "people": lambda r: {"company_id": r["company_id"], "email": r["email"]},
    }

    for name in ("companies", "jobs", "people", "applications", "outreach", "runs"):
        rows = tables[name]
        n = 0
        for row in rows:
            doc = {k: v for k, v in row.items()}
            key = natural_key.get(name, lambda r: {"id": r["id"]})(row)
            db[name].update_one(key, {"$set": doc}, upsert=True)
            n += 1
        written[name] = n
        print(f"   {name:<14} {n:>5}")

    # Sequences must resume above the highest id we just imported, or the next
    # insert would collide with a migrated row.
    for name in ("companies", "jobs", "people", "applications", "outreach", "runs"):
        top = max((int(r["id"]) for r in tables[name] if r.get("id") is not None), default=0)
        current = (db.counters.find_one({"_id": name}) or {}).get("seq", 0)
        if top > current:
            db.counters.update_one({"_id": name}, {"$set": {"seq": top}}, upsert=True)
    print("\n[ok] id sequences advanced past the imported rows.")

    print("\nverifying:")
    for name in COLLECTIONS:
        print(f"   {name:<14} {db[name].count_documents({}):>5} in MongoDB")

    print(f"\n[done] The agent now reads and writes MongoDB. {src.name} is left "
          f"untouched as a backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
