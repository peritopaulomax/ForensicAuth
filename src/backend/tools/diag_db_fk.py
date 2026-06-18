"""Lista FKs SQLite e testa exclusao de caso."""
import sqlite3
import uuid

DB = "forensicauth_dev.db"


def main() -> None:
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()
    for table in ("custody_records", "analysis_jobs", "evidences", "reports", "cases"):
        print(f"\n== {table} ==")
        cur.execute(f"PRAGMA foreign_key_list({table})")
        for row in cur.fetchall():
            print(row)
    cur.execute(
        "SELECT id, protocol_number, deleted_at FROM cases WHERE title LIKE '%Exemplo%' OR protocol_number LIKE '%1234%'"
    )
    print("\ncases:", cur.fetchall())
    conn.close()


if __name__ == "__main__":
    main()
