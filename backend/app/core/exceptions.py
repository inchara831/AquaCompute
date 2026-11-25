"""Domain exceptions mapped cleanly to HTTP error responses."""

from __future__ import annotations


class AquaComputeError(Exception):
    """Base application exception."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(AquaComputeError):
    """Raised when required environment/AWS configuration is missing or invalid."""

    status_code = 503
    error_code = "configuration_required"

    def __init__(self, message: str, *, missing_fields: list[str] | None = None) -> None:
        super().__init__(message, details={"missing_fields": missing_fields or []})


class AwsCredentialsError(AquaComputeError):
    """Raised when AWS credentials are unavailable or expired."""

    status_code = 503
    error_code = "aws_credentials_unavailable"


class AwsPermissionError(AquaComputeError):
    """Raised when IAM permissions are insufficient for an AWS API call."""

    status_code = 403
    error_code = "aws_permission_denied"


class AwsThrottlingError(AquaComputeError):
    """Raised when AWS throttles API calls after retries."""

    status_code = 429
    error_code = "aws_throttled"


class ResourceNotFoundError(AquaComputeError):
    """Raised when a target EC2 instance, table, or object cannot be found."""

    status_code = 404
    error_code = "resource_not_found"


class MetricUnavailableError(AquaComputeError):
    """Raised when CloudWatch returns an error or metrics cannot be retrieved."""

    status_code = 502
    error_code = "metrics_unavailable"


class BedrockNotConfiguredError(AquaComputeError):
    """Raised when AquaMind RAG is invoked without Bedrock KB configuration."""

    status_code = 503
    error_code = "bedrock_not_configured"


class FootprintNotIntegratedError(AquaComputeError):
    """Raised until Person 2 integrates a documented water footprint calculator."""

    status_code = 501
    error_code = "footprint_calculator_not_integrated"
