"""Reusable enterprise authentication primitives.

The package intentionally knows nothing about DSP resources or application
roles.  DSP-specific identity resolution and authorization live in
``app.auth`` so this package can be extracted without rewriting consumers.
"""

from enterprise_auth.models import AuthenticatedIdentity, IssuedAccessToken

__all__ = ["AuthenticatedIdentity", "IssuedAccessToken"]
