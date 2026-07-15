"""Shared base class for Sprint 1+ domain models.

Every domain model inherits from this instead of `pydantic.BaseModel`
directly, so that unknown fields are rejected and assignments are
revalidated the same way everywhere, instead of each model configuring
this individually.
"""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base class enforcing strict field and mutation validation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
