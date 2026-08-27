"""Stable errors exposed by the reusable authentication boundary."""


class AuthenticationError(Exception):
    """Base class for a rejected authentication operation."""


class AuthenticationConfigurationError(AuthenticationError):
    """Required provider or token material is absent or inconsistent."""


class InvalidCredentials(AuthenticationError):
    """A local username/password pair could not be authenticated."""


class PasswordChangeRequired(AuthenticationError):
    """A local account must complete its governed setup/reset action."""


class SamlResponseRejected(AuthenticationError):
    """Ping returned a SAML response that did not pass validation."""


class TokenRejected(AuthenticationError):
    """An application access token did not pass validation."""
