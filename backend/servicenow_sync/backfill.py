"""
One-time (or repeatable) bulk import: pulls every ticket currently in
ServiceNow and upserts it into the local `servicenow_tickets` Postgres table.

Usage (from backend/):
    python -m servicenow_sync.backfill
"""
from . import client, db


def run():
    batch = []
    total = 0

    for record in client.fetch_all_records():
        batch.append(record)
        if len(batch) >= 100:
            total += db.upsert_tickets(batch)
            print(f"Synced {total} tickets so far...")
            batch = []

    if batch:
        total += db.upsert_tickets(batch)

    print(f"Done. Synced {total} tickets into servicenow_tickets.")


if __name__ == "__main__":
    run()
