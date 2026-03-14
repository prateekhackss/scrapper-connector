"""
ConnectorOS Scout — Custom Exceptions

Centralised error hierarchy so every module raises typed errors
that the middleware and pipeline can handle gracefully.
"""


class ConnectorOSError(Exception):
    """Base exception for all ConnectorOS errors."""

    def __init__(self, message: str = "An unexpected error occurred.", details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class APIError(ConnectorOSError):
    """Raised when an external API call fails (OpenAI, SerpAPI, etc.)."""

    def __init__(self, api_name: str, message: str, status_code: int | None = None, details: str | None = None):
        self.api_name = api_name
        self.status_code = status_code
        super().__init__(f"[{api_name}] {message}", details)


class RateLimitError(APIError):
    """Raised when an external API returns 429 (rate limited)."""

    def __init__(self, api_name: str, retry_after: int | None = None):
        self.retry_after = retry_after
        msg = f"Rate limited by {api_name}."
        if retry_after:
            msg += f" Retry after {retry_after}s."
        super().__init__(api_name, msg, status_code=429)


class BudgetExceededError(ConnectorOSError):
    """Raised when daily OpenAI spend exceeds the configured budget."""

    def __init__(self, spent: float, budget: float):
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"Daily budget exceeded: ${spent:.2f} spent of ${budget:.2f} limit.",
            details="Non-critical API calls will be skipped until tomorrow.",
        )


class ValidationError(ConnectorOSError):
    """Raised when data fails Pydantic or business-logic validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"Validation error on '{field}': {message}")


class DatabaseError(ConnectorOSError):
    """Raised when a database operation fails."""

    def __init__(self, operation: str, message: str):
        self.operation = operation
        super().__init__(f"Database error during {operation}: {message}")


class PipelineError(ConnectorOSError):
    """Raised when the pipeline orchestrator encounters a fatal error."""

    def __init__(self, stage: str, message: str, details: str | None = None):
        self.stage = stage
        super().__init__(f"Pipeline failed at stage '{stage}': {message}", details)
