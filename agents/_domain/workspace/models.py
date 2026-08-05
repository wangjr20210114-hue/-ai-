"""Workspace domain errors."""


class WorkspaceConflictError(RuntimeError):
    """Raised instead of silently overwriting a newer user workspace."""


class WorkspaceSnapshotError(RuntimeError):
    """Raised when an action payload no longer matches its sealed snapshot."""
