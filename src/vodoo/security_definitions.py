"""Cycle-free value types used by generated security definitions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessDefinition:
    """Access control entry for a model."""

    model: str
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool


@dataclass(frozen=True)
class RuleDefinition:
    """Record rule definition for a model."""

    model: str
    domain: str
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool


@dataclass(frozen=True)
class GroupDefinition:
    """Security group definition."""

    name: str
    comment: str
    access: tuple[AccessDefinition, ...]
    rules: tuple[RuleDefinition, ...] = ()
