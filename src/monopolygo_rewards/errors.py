"""Errors whose messages are safe to display without raw browser details."""


class RewardsError(RuntimeError):
    """An expected operational failure."""


class ConfigurationError(RewardsError):
    """Invalid user configuration."""


class SessionError(RewardsError):
    """Missing or unusable authentication cookies."""


class WorkflowError(RewardsError):
    """The page could not safely complete the workflow."""


class AuthenticationError(WorkflowError):
    """Authentication or exact account identity was rejected."""
