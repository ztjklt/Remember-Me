"""Provider adapters for structured AI Core output."""

from .base import ModelRequest, StructuredModelProvider
from .fixture import FixtureProvider
from .openai_compatible import OpenAICompatibleProvider

__all__ = [
    "FixtureProvider",
    "ModelRequest",
    "OpenAICompatibleProvider",
    "StructuredModelProvider",
]
