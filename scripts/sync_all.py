#!/usr/bin/env python3
"""Sync all configured integrations.

Usage:
    python -m scripts.sync_all
    # or
    python scripts/sync_all.py
"""
import json
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.integrations.sync import sync_all


def main():
    print("Syncing all configured integrations...")
    results = sync_all()

    if not results:
        print("No enabled connectors found. Configure integrations via the API first.")
        return

    for r in results:
        status = "OK" if not r.errors else "ERRORS"
        print(f"  [{status}] {r.connector}: {r.accounts_synced} accounts, "
              f"{r.signals_synced} signals ({r.duration_seconds}s)")
        for err in r.errors:
            print(f"    ERROR: {err}")

    total_accts = sum(r.accounts_synced for r in results)
    total_errors = sum(len(r.errors) for r in results)
    print(f"\nDone. {total_accts} accounts synced, {total_errors} errors.")


if __name__ == "__main__":
    main()
