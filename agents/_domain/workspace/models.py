"""Workspace domain errors."""


class WorkspaceConflictError(RuntimeError):
    """Raised instead of silently overwriting a newer user workspace."""
