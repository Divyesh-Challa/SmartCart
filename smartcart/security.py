"""HTTP hardening: rate limiting, security headers and request size limits."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from smartcart.config import get_settings


def rate_limit_key(request: Request) -> str:
    """Signed-in users are limited per account; everyone else per client IP."""
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


_settings = get_settings()
limiter = Limiter(
    key_func=rate_limit_key,
    default_limits=[_settings.rate_limit_default],
    enabled=_settings.rate_limit_enabled,
    headers_enabled=False,
)


# On-device receipt OCR (Tesseract.js) loads its worker, WebAssembly core and
# language data from jsDelivr, and starts the worker from a blob: URL.
OCR_CDN = "https://cdn.jsdelivr.net"
PRODUCT_IMAGES = "https://images.openfoodfacts.org"


def web_app_csp() -> str:
    """Content-Security-Policy for the web app's pages: only our own code, plus the few services it needs."""
    connect = ["'self'", OCR_CDN]
    supabase = get_settings().supabase_url
    if supabase:
        origin = supabase.rstrip("/")
        connect += [origin, origin.replace("https://", "wss://", 1)]
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {OCR_CDN} 'wasm-unsafe-eval'",
        "worker-src 'self' blob:",
        f"connect-src {' '.join(connect)}",
        f"img-src 'self' data: blob: {PRODUCT_IMAGES}",
        "style-src 'self' 'unsafe-inline'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        else:
            response.headers.setdefault("Content-Security-Policy", web_app_csp())
        if get_settings().is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class MaxBodySizeMiddleware:
    """
    Rejects request bodies over SMARTCART_MAX_REQUEST_BYTES with 413. Checks the
    declared Content-Length up front, and also counts bytes as they arrive so
    chunked uploads (no Content-Length) can't get past the limit.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().max_request_bytes
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(scope, receive, send)
            return

        received = 0
        response_started = False
        rejected = False

        async def counting_receive():
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit and not response_started:
                    # Answer now and tell the app the client went away, so it stops reading.
                    rejected = True
                    await self._reject(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            nonlocal response_started
            if rejected:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except Exception:
            if not rejected:
                raise

    @staticmethod
    async def _reject(scope, receive, send):
        await JSONResponse({"detail": "Request body too large."}, status_code=413)(scope, receive, send)
