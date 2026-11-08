"""Shared Pydantic base model for configuration DTOs.

Configuration DTOs import this lightweight module without loading the root schema.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
