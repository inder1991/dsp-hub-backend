"""HTTP-level authentication controls shared by every provider route."""

from __future__ import annotations

from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import get_settings

_AUTH_POSTS = {
    "/auth/exchange",
    "/auth/local/login",
    "/auth/local/password-action",
    "/auth/refresh",
    "/auth/logout",
}

_JSON_BODY_POSTS = {
    "/auth/exchange",
    "/auth/local/login",
    "/auth/local/password-action",
}


class AuthenticationSecurityMiddleware(BaseHTTPMiddleware):
    """Apply correlation, request-shape, origin, and response-header policy."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        request.state.correlation_id = correlation_id[:80]
        rejection = await self._validate_request(request)
        response = rejection or await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/auth"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    async def _validate_request(self, request: Request) -> Response | None:
        if request.method != "POST" or not request.url.path.startswith("/auth"):
            return None
        settings = get_settings()
        is_saml = request.url.path == "/auth/saml/acs"
        limit = settings.saml_body_limit_bytes if is_saml else settings.auth_json_body_limit_bytes
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > limit:
                    return self._error(413, "Authentication request is too large")
            except ValueError:
                return self._error(400, "Invalid Content-Length header")
        body = await request.body()
        if len(body) > limit:
            return self._error(413, "Authentication request is too large")

        content_type = request.headers.get("content-type", "").lower()
        if is_saml:
            if not content_type.startswith("application/x-www-form-urlencoded"):
                return self._error(415, "SAML response must use form encoding")
            return None

        if request.url.path in _AUTH_POSTS or request.url.path.startswith("/auth/admin/"):
            requires_json = request.url.path in _JSON_BODY_POSTS or request.url.path.startswith(
                "/auth/admin/"
            )
            if requires_json and not content_type.startswith("application/json"):
                return self._error(415, "Authentication request must use JSON")
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in settings.approved_origin_list:
                return self._error(403, "Request origin is not permitted")
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site and fetch_site != "same-origin":
                return self._error(403, "Cross-site authentication request is not permitted")
        return None

    @staticmethod
    def _error(status_code: int, detail: str) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": detail})
