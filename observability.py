"""Structured logging and request correlation.

Turns the app's plain stdout logging into JSON with a per-request correlation id
when ``ATIS_LOG_JSON=1`` (recommended in production so a log aggregator can parse
and correlate). Development keeps human-readable logs by default.

Every request is tagged with a request id: the inbound ``X-Request-ID`` header is
honoured (so an upstream proxy / load balancer trace id flows through) or a new
one is minted. The id is attached to ``g``, echoed back in the ``X-Request-ID``
response header, and included on every log line emitted during the request.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid

from flask import g, request


def _json_logging_enabled() -> bool:
    raw = os.environ.get("ATIS_LOG_JSON", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class RequestIdFilter(logging.Filter):
    """Inject the current request id (or '-') onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.request_id = g.get("request_id", "-")
        except Exception:  # noqa: BLE001 - outside a request context
            record.request_id = "-"
        return True


class JsonFormatter(logging.Formatter):
    """Minimal, dependency-free JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(flask_app) -> None:
    """Configure log format and per-request correlation ids."""
    request_id_filter = RequestIdFilter()

    if _json_logging_enabled():
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(request_id_filter)
        # Replace default handlers on the app, werkzeug, and root loggers so
        # access logs and app logs share the JSON format + request id. The app
        # and werkzeug loggers stop propagating so a record isn't also emitted by
        # the root handler (which would double every line).
        for logger in (flask_app.logger, logging.getLogger("werkzeug")):
            logger.handlers = [handler]
            logger.setLevel(logging.INFO)
            logger.propagate = False
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
    else:
        # Human-readable dev format, still carrying the request id.
        for handler in flask_app.logger.handlers or [logging.StreamHandler()]:
            handler.addFilter(request_id_filter)

    @flask_app.before_request
    def _assign_request_id():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

    @flask_app.after_request
    def _echo_request_id(response):
        response.headers.setdefault("X-Request-ID", g.get("request_id", "-"))
        return response
