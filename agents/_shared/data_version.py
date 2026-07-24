"""Single source of truth for the clean Makers data generation.

Changing this value starts a logically empty application without deleting the
previous Makers-managed Conversation, Checkpointer, or LangGraph Store data.
"""

from __future__ import annotations

import hashlib
import re


DATA_GENERATION = "v6_20260724_reset"
# Conversation and file generations can be advanced independently when the
# owner wants a clean demo without erasing schedules, memories or preferences.
FILE_DATA_GENERATION = "v7_20260724_clear"
# Makers requires every makers-conversation-id to be 6-36 characters. Keep the
# generation marker short and hash unexpected legacy IDs so all direct Agent
# calls satisfy the platform contract.
CONVERSATION_PREFIX = "yb7_"
BLOB_GENERATION_PATH = f"{FILE_DATA_GENERATION}/"


def namespace(name: str, *parts: str) -> tuple[str, ...]:
    return (f"yuanbao_{name}_{DATA_GENERATION}", *(str(part) for part in parts))


def scoped_conversation(raw: str) -> str:
    clean = str(raw or "").strip()
    candidate = clean if clean.startswith(CONVERSATION_PREFIX) else f"{CONVERSATION_PREFIX}{clean}"
    if len(candidate) <= 36 and re.fullmatch(r"[0-9A-Za-z._-]+", candidate):
        return candidate
    return f"{CONVERSATION_PREFIX}{hashlib.sha256(clean.encode('utf-8')).hexdigest()[:32]}"
