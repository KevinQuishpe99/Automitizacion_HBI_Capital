"""Utilidades compartidas para locks con TTL (Memory + Vercel Blob)."""

from __future__ import annotations

from datetime import datetime, timezone


def parse_expires_at(expires_at: str | None) -> datetime | None:
    if not expires_at:
        return None
    try:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp
    except ValueError:
        return None


def is_lock_expired(expires_at: str | None) -> bool:
    """True si expiró o si expires_at es inválido (locks huérfanos se tratan como expirados)."""
    exp = parse_expires_at(expires_at)
    if exp is None:
        return bool(expires_at)
    return datetime.now(timezone.utc) >= exp


def seconds_until_expiry(expires_at: str | None) -> int | None:
    exp = parse_expires_at(expires_at)
    if exp is None:
        return None
    delta = exp - datetime.now(timezone.utc)
    return int(delta.total_seconds())
