"""Security response headers.

Adds the standard hardening headers the app was missing: a Content-Security
-Policy (which also carries the clickjacking defence via ``frame-ancestors``),
``X-Content-Type-Options``, ``Referrer-Policy``, ``Permissions-Policy`` and, in
production, HSTS.

Framing is configurable because in production ATIS is deliberately embedded in a
cross-site iframe (e.g. Hugging Face Spaces — see the SameSite cookie note in
``config.py``). ``ATIS_FRAME_ANCESTORS`` sets who may frame the app; it defaults
to ``'self'``. The CSP always drives framing policy; the legacy
``X-Frame-Options`` header is only emitted when it can faithfully represent the
setting (browsers that honour CSP ``frame-ancestors`` ignore it anyway).
"""

from __future__ import annotations

import os


def _frame_ancestors() -> str:
    return os.environ.get("ATIS_FRAME_ANCESTORS", "'self'").strip() or "'self'"


def _build_csp(frame_ancestors: str) -> str:
    # style-src allows 'unsafe-inline' because templates use inline style="…"
    # attributes; script execution stays locked to first-party files. The only
    # inline <script> is a non-executable application/json data island.
    # Fonts are self-hosted (static/fonts + static/css/fonts.css), so style-src /
    # font-src stay first-party. style-src keeps 'unsafe-inline' for the inline
    # style="…" attributes in templates; scripts remain locked to 'self'.
    directives = [
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "img-src 'self' data:",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        f"frame-ancestors {frame_ancestors}",
    ]
    return "; ".join(directives)


def register_security_headers(flask_app):
    """Attach hardening headers to every response."""
    is_production = flask_app.config["IS_PRODUCTION"]
    frame_ancestors = _frame_ancestors()
    csp = os.environ.get("ATIS_CSP") or _build_csp(frame_ancestors)

    @flask_app.after_request
    def set_security_headers(response):
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            # The live-feed page legitimately needs the camera; everything else off.
            "camera=(self), microphone=(), geolocation=(), interest-cohort=()",
        )

        # X-Frame-Options can only express same-origin/deny, so only emit it when
        # the frame policy is one of those; otherwise CSP frame-ancestors governs.
        if frame_ancestors == "'self'":
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        elif frame_ancestors in {"'none'", "none"}:
            response.headers.setdefault("X-Frame-Options", "DENY")

        # HSTS only in production (dev serves plain http); assumes TLS at the edge.
        if is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
