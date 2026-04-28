from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float


# Conservative estimate table; can be overridden later by provider-fed values.
PRICING_BY_MODEL: dict[str, ModelPricing] = {
    "local_echo": ModelPricing(input_per_million_usd=0.0),
    "gpt-4.1-mini": ModelPricing(input_per_million_usd=0.80),
    "gpt-4.1": ModelPricing(input_per_million_usd=3.00),
    "gpt-4o-mini": ModelPricing(input_per_million_usd=0.60),
    "gpt-4o": ModelPricing(input_per_million_usd=2.50),
    "gpt-5.2": ModelPricing(input_per_million_usd=2.00),
    "gpt-5.4": ModelPricing(input_per_million_usd=3.50),
    "claude-3-5-sonnet": ModelPricing(input_per_million_usd=3.00),
    "claude-3-haiku": ModelPricing(input_per_million_usd=0.80),
    "gemini-1.5-pro": ModelPricing(input_per_million_usd=3.50),
    "gemini-1.5-flash": ModelPricing(input_per_million_usd=0.35),
}


def estimate_input_cost_usd(*, model: str, input_tokens: int) -> float | None:
    pricing = PRICING_BY_MODEL.get(model.strip())
    if pricing is None:
        return None
    if input_tokens <= 0:
        return 0.0
    return round((input_tokens / 1_000_000.0) * pricing.input_per_million_usd, 8)
