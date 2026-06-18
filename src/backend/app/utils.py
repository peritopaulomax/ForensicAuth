"""Utility functions for the backend application."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-naive datetime.

    SQLite does not store timezone information, so we strip it
    to keep consistency between inserts and reads.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
