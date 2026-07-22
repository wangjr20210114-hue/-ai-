"""Single source of truth for the clean Makers data generation.

Changing this value starts a logically empty application without deleting the
previous Makers-managed Conversation, Checkpointer, or LangGraph Store data.
"""

from __future__ import annotations


DATA_GENERATION = "v5_20260722_clean"
CONVERSATION_PREFIX = f"yuanbao_{DATA_GENERATION}_"
BLOB_GENERATION_PATH = f"{DATA_GENERATION}/"


def namespace(name: str, *parts: str) -> tuple[str, ...]:
    return (f"yuanbao_{name}_{DATA_GENERATION}", *(str(part) for part in parts))


def scoped_conversation(raw: str) -> str:
    clean = str(raw or "").strip()
    return clean if clean.startswith(CONVERSATION_PREFIX) else f"{CONVERSATION_PREFIX}{clean}"
