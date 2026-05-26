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


def lock_granted_ttl_seconds(
    *,
    created_at: str | None,
    expires_at: str | None,
) -> int | None:
    """Duración TTL con la que se emitió el lock (created_at → expires_at)."""
    created = parse_expires_at(created_at)
    expires = parse_expires_at(expires_at)
    if created is None or expires is None:
        return None
    return int((expires - created).total_seconds())


def is_legacy_oversized_lock(
    record: dict | None,
    *,
    configured_ttl_seconds: int,
) -> bool:
    """
    True si el lock se creó con una política TTL antigua (p. ej. 86400 s)
    mayor que la configuración actual (p. ej. 900 s).
    """
    if not record:
        return False
    granted = lock_granted_ttl_seconds(
        created_at=record.get("created_at"),
        expires_at=record.get("expires_at"),
    )
    if granted is None:
        remaining = seconds_until_expiry(record.get("expires_at"))
        if remaining is None:
            return False
        return remaining > configured_ttl_seconds * 2
    slack = max(60, int(configured_ttl_seconds * 0.1))
    return granted > configured_ttl_seconds + slack


def should_relinquish_lock(
    record: dict | None,
    *,
    configured_ttl_seconds: int,
) -> bool:
    """El lock debe eliminarse: expiró o es legacy con TTL demasiado largo."""
    if not record:
        return False
    if is_lock_expired(record.get("expires_at")):
        return True
    return is_legacy_oversized_lock(record, configured_ttl_seconds=configured_ttl_seconds)
