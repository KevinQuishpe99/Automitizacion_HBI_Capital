"""Smoke checks en build Vercel: falla antes del runtime si faltan dependencias."""

from __future__ import annotations

import sys


def main() -> int:
    import fastapi

    print(f"fastapi ok ({fastapi.__version__})")

    from index import app

    print(f"index import ok ({type(app).__name__})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
