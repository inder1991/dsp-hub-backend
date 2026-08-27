"""Create the first governed local administrator from temporary environment values.

Run after migrations with ``python -m app.auth.bootstrap``. The command refuses
to add another bootstrap account when an active local administrator exists.
"""

from __future__ import annotations

from app.auth.db import get_session_factory
from app.auth.repository import AuthRepository
from app.core.config import get_settings
from enterprise_auth.passwords import PasswordService


def main() -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_username or not settings.bootstrap_admin_password:
        raise SystemExit("DSP_BOOTSTRAP_ADMIN_USERNAME and DSP_BOOTSTRAP_ADMIN_PASSWORD are required")
    if len(settings.bootstrap_admin_password) < settings.local_password_min_length:
        raise SystemExit(
            "Bootstrap administrator password must contain at least "
            f"{settings.local_password_min_length} characters"
        )
    with get_session_factory()() as session:
        repository = AuthRepository(session)
        if repository.count_active_admins() > 0:
            raise SystemExit("An active local administrator already exists; bootstrap was not applied")
        account = repository.create_local_account(
            username=settings.bootstrap_admin_username,
            display_name=settings.bootstrap_admin_display_name,
            email=None,
            password_hash=PasswordService().hash(settings.bootstrap_admin_password),
            role="ADMIN",
            must_change_password=False,
            performed_by=None,
        )
        created_username = account.principal.username
    print(f"Created bootstrap administrator {created_username!r}")


if __name__ == "__main__":
    main()
