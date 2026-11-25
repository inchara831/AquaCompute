"""Structured JSON logging with secret redaction and optional CloudWatch Logs shipping."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(AKIA|ASIA|AROA|AIDA)[0-9A-Z]{16}"), "[REDACTED_AWS_KEY_ID]"),
    (re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)(aws_secret_access_key|secret_access_key|aws_session_token|session_token|authorization|token|password)\s*[:=]\s*['\"]?[^\s'\",;}{]+['\"]?"
        ),
        r"\1=[REDACTED]",
    ),
]


def redact_secrets(text: str) -> str:
    """Mask AWS keys, tokens, and credential-like key=value patterns in log strings."""
    sanitized = text
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class SecretRedactingFilter(logging.Filter):
    """Logging filter that redacts secrets from message and structured args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a for a in record.args
                )
        return True


class JsonLogFormatter(logging.Formatter):
    """Formats log records as single-line JSON for CloudWatch Logs compatibility."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload["context"] = {
                k: redact_secrets(str(v)) if isinstance(v, str) else v
                for k, v in extra_fields.items()
            }
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


class CloudWatchLogHandler(logging.Handler):
    """Ships structured logs to AWS CloudWatch Logs without breaking app requests on error."""

    def __init__(self, logs_client: Any, log_group: str, log_stream: str) -> None:
        super().__init__()
        self._client = logs_client
        self._log_group = log_group
        self._log_stream = log_stream
        self._stream_ensured = False

    def _ensure_group_and_stream(self) -> None:
        if self._stream_ensured:
            return
        try:
            self._client.create_log_group(logGroupName=self._log_group)
        except Exception:
            pass
        try:
            self._client.create_log_stream(
                logGroupName=self._log_group, logStreamName=self._log_stream
            )
        except Exception:
            pass
        self._stream_ensured = True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_group_and_stream()
            message = self.format(record)
            timestamp_ms = int(record.created * 1000)
            self._client.put_log_events(
                logGroupName=self._log_group,
                logStreamName=self._log_stream,
                logEvents=[{"timestamp": timestamp_ms, "message": message}],
            )
        except Exception:
            # Never raise from logging handler; local stderr handler preserves visibility.
            pass


def configure_logging(
    level: str = "INFO",
    *,
    cloudwatch_handler: logging.Handler | None = None,
) -> logging.Logger:
    """Configure root AquaCompute logger with JSON formatting and secret redaction."""
    root_logger = logging.getLogger("aquacompute")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()
    root_logger.propagate = False

    formatter = JsonLogFormatter()
    redactor = SecretRedactingFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    root_logger.addHandler(stream_handler)

    if cloudwatch_handler is not None:
        cloudwatch_handler.setFormatter(formatter)
        cloudwatch_handler.addFilter(redactor)
        root_logger.addHandler(cloudwatch_handler)

    return root_logger
