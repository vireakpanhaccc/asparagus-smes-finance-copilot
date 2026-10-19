"""Tool registry. Every tool declares its permission tier here, in code.

The tier is enforced by app.policy.engine on the server, never by the prompt.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Tier(str, Enum):
    READ_ONLY = "read_only"  # reads data, runs freely
    SUGGEST = "suggest"  # drafts/recommends, nothing leaves the app
    NEEDS_APPROVAL = "needs_approval"  # sends, submits or moves money


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    tier: Tier
    input_model: type[BaseModel]
    handler: Callable[..., Any]  # handler(session, validated_input) -> JSON-able
    # NEEDS_APPROVAL only: builds the payload the owner approves from server records
    # (e.g. payee and amount of a bill). Re-run at execution; any difference blocks it.
    prepare: Callable[..., dict[str, Any]] | None = None

    def to_llm_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": f"[{self.tier.value}] {self.description}",
            "input_schema": self.input_model.model_json_schema(),
        }


REGISTRY: dict[str, ToolSpec] = {}


def tool(
    *,
    name: str,
    description: str,
    tier: Tier,
    input_model: type[BaseModel],
    prepare: Callable[..., dict[str, Any]] | None = None,
):
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in REGISTRY:
            raise ValueError(f"duplicate tool name: {name}")
        REGISTRY[name] = ToolSpec(name, description, tier, input_model, fn, prepare)
        return fn

    return decorator
