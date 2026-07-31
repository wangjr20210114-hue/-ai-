"""Least-privilege application ports exposed to trusted system Skills."""

from .runtime_ports import (
    SERVICE_PERMISSIONS,
    SkillServices,
)

__all__ = ("SERVICE_PERMISSIONS", "SkillServices")

