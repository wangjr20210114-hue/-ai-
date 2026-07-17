"""Normalized Agent and provider error classification."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentErrorInfo:
    code: str
    message: str
    retryable: bool = False
    reconciliation_required: bool = False


class BudgetExceededError(RuntimeError):
    """The configured daily budget would be exceeded."""


class UnknownSideEffectResult(RuntimeError):
    """The external request may have succeeded but its response was lost."""


class ProviderError(RuntimeError):
    """Base class for normalized model or external provider failures."""


class ProviderAuthenticationError(ProviderError):
    """Provider credentials are invalid or lack permission."""


class ProviderRateLimitError(ProviderError):
    """Provider rate limit or temporary quota guard was reached."""


class ProviderTimeoutError(ProviderError):
    """Provider did not complete the request within the configured timeout."""


class ProviderResponseError(ProviderError):
    """Provider returned an invalid or unexpected response."""


def classify_exception(error: Exception) -> AgentErrorInfo:
    name = type(error).__name__
    text = str(error) or name
    if name == "QuotaExhaustedError":
        return AgentErrorInfo("quota_exhausted", text, retryable=False)
    if isinstance(error, BudgetExceededError):
        return AgentErrorInfo("budget_exceeded", text, retryable=False)
    if name == "ApiNotConfiguredError":
        return AgentErrorInfo("provider_not_configured", text, retryable=False)
    if isinstance(error, ProviderAuthenticationError):
        return AgentErrorInfo("provider_authentication_failed", text, retryable=False)
    if isinstance(error, ProviderRateLimitError):
        return AgentErrorInfo("provider_rate_limited", text, retryable=True)
    if isinstance(error, ProviderTimeoutError):
        return AgentErrorInfo("provider_timeout", text, retryable=True)
    if isinstance(error, ProviderResponseError):
        return AgentErrorInfo("provider_response_invalid", text, retryable=False)
    if isinstance(error, UnknownSideEffectResult):
        return AgentErrorInfo(
            "unknown_side_effect_result",
            text,
            retryable=False,
            reconciliation_required=True,
        )
    if isinstance(error, TimeoutError):
        return AgentErrorInfo("timeout", text, retryable=True)
    if isinstance(error, (ConnectionError, OSError)):
        return AgentErrorInfo("provider_unavailable", text, retryable=True)
    return AgentErrorInfo("execution_failed", text, retryable=False)
