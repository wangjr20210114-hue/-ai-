"""Compatibility import for the chat StreamPresenter progress contract.

Remove this module after all legacy routes import from ``agents._presenters``.
"""

from agents._presenters.chat_stream import progress_event, tool_progress_event

__all__ = ("progress_event", "tool_progress_event")
