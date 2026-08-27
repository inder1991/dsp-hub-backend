"""Delete expired authentication state in bounded, retryable batches."""

from __future__ import annotations

from app.auth.db import get_session_factory
from app.auth.repository import AuthRepository
from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    with get_session_factory()() as session:
        deleted = AuthRepository(session).cleanup_expired_auth_state(settings.auth_cleanup_batch_size)
    summary = ", ".join(f"{table}={count}" for table, count in sorted(deleted.items()))
    print(f"Authentication cleanup complete: {summary}")


if __name__ == "__main__":
    main()
