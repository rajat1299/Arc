"""Static model pricing catalog and deterministic cost computation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from opscanvas_core.events import Usage

PRICE_CATALOG_SNAPSHOT_DATE = "2026-04-27"

_TOKENS_PER_MILLION = Decimal("1000000")
_USD_QUANTUM = Decimal("0.0000000001")

_OPENAI_PRICING_URL = "https://openai.com/api/pricing/"
_ANTHROPIC_PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
_GOOGLE_PRICING_URL = "https://ai.google.dev/gemini-api/docs/pricing"


@dataclass(frozen=True, slots=True)
class PriceTier:
    """Per-1M-token prices for one context tier."""

    input_usd_per_1m: Decimal
    output_usd_per_1m: Decimal
    cached_input_usd_per_1m: Decimal | None = None
    max_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Immutable catalog entry for one normalized provider/model pair."""

    provider: str
    model: str
    source_url: str
    tiers: tuple[PriceTier, ...]


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    """Rounded USD cost components for a single usage/model/provider tuple."""

    provider: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    input_cost_usd: Decimal
    cached_input_cost_usd: Decimal
    output_cost_usd: Decimal
    total_cost_usd: Decimal


def _tier(
    input_usd_per_1m: str,
    output_usd_per_1m: str,
    cached_input_usd_per_1m: str | None,
    *,
    max_input_tokens: int | None = None,
) -> PriceTier:
    return PriceTier(
        input_usd_per_1m=Decimal(input_usd_per_1m),
        cached_input_usd_per_1m=(
            Decimal(cached_input_usd_per_1m) if cached_input_usd_per_1m is not None else None
        ),
        output_usd_per_1m=Decimal(output_usd_per_1m),
        max_input_tokens=max_input_tokens,
    )


def _price(
    provider: str,
    model: str,
    source_url: str,
    *tiers: PriceTier,
) -> ModelPrice:
    return ModelPrice(provider=provider, model=model, source_url=source_url, tiers=tiers)


MODEL_PRICES: Mapping[tuple[str, str], ModelPrice] = MappingProxyType(
    {
        ("openai", "gpt-5.5"): _price(
            "openai", "gpt-5.5", _OPENAI_PRICING_URL, _tier("5.00", "30.00", "0.50")
        ),
        ("openai", "gpt-5.4"): _price(
            "openai", "gpt-5.4", _OPENAI_PRICING_URL, _tier("2.50", "15.00", "0.25")
        ),
        ("openai", "gpt-5.4-mini"): _price(
            "openai", "gpt-5.4-mini", _OPENAI_PRICING_URL, _tier("0.75", "4.50", "0.075")
        ),
        ("anthropic", "claude-opus-4.7"): _price(
            "anthropic",
            "claude-opus-4.7",
            _ANTHROPIC_PRICING_URL,
            _tier("5.00", "25.00", "0.50"),
        ),
        ("anthropic", "claude-opus-4.6"): _price(
            "anthropic",
            "claude-opus-4.6",
            _ANTHROPIC_PRICING_URL,
            _tier("5.00", "25.00", "0.50"),
        ),
        ("anthropic", "claude-opus-4.5"): _price(
            "anthropic",
            "claude-opus-4.5",
            _ANTHROPIC_PRICING_URL,
            _tier("5.00", "25.00", "0.50"),
        ),
        ("anthropic", "claude-opus-4.1"): _price(
            "anthropic",
            "claude-opus-4.1",
            _ANTHROPIC_PRICING_URL,
            _tier("15.00", "75.00", "1.50"),
        ),
        ("anthropic", "claude-opus-4"): _price(
            "anthropic",
            "claude-opus-4",
            _ANTHROPIC_PRICING_URL,
            _tier("15.00", "75.00", "1.50"),
        ),
        ("anthropic", "claude-sonnet-4.6"): _price(
            "anthropic",
            "claude-sonnet-4.6",
            _ANTHROPIC_PRICING_URL,
            _tier("3.00", "15.00", "0.30"),
        ),
        ("anthropic", "claude-sonnet-4.5"): _price(
            "anthropic",
            "claude-sonnet-4.5",
            _ANTHROPIC_PRICING_URL,
            _tier("3.00", "15.00", "0.30"),
        ),
        ("anthropic", "claude-sonnet-4"): _price(
            "anthropic",
            "claude-sonnet-4",
            _ANTHROPIC_PRICING_URL,
            _tier("3.00", "15.00", "0.30"),
        ),
        ("anthropic", "claude-sonnet-3.7"): _price(
            "anthropic",
            "claude-sonnet-3.7",
            _ANTHROPIC_PRICING_URL,
            _tier("3.00", "15.00", "0.30"),
        ),
        ("anthropic", "claude-haiku-4.5"): _price(
            "anthropic",
            "claude-haiku-4.5",
            _ANTHROPIC_PRICING_URL,
            _tier("1.00", "5.00", "0.10"),
        ),
        ("anthropic", "claude-haiku-3.5"): _price(
            "anthropic",
            "claude-haiku-3.5",
            _ANTHROPIC_PRICING_URL,
            _tier("0.80", "4.00", "0.08"),
        ),
        ("anthropic", "claude-haiku-3"): _price(
            "anthropic",
            "claude-haiku-3",
            _ANTHROPIC_PRICING_URL,
            _tier("0.25", "1.25", "0.03"),
        ),
        ("google", "gemini-3-flash-preview"): _price(
            "google",
            "gemini-3-flash-preview",
            _GOOGLE_PRICING_URL,
            _tier("0.50", "3.00", "0.05"),
        ),
        ("google", "gemini-2.5-pro"): _price(
            "google",
            "gemini-2.5-pro",
            _GOOGLE_PRICING_URL,
            _tier("1.25", "10.00", "0.125", max_input_tokens=200_000),
            _tier("2.50", "15.00", "0.25"),
        ),
        ("google", "gemini-2.5-flash"): _price(
            "google",
            "gemini-2.5-flash",
            _GOOGLE_PRICING_URL,
            _tier("0.30", "2.50", "0.03"),
        ),
        ("google", "gemini-2.5-flash-lite"): _price(
            "google",
            "gemini-2.5-flash-lite",
            _GOOGLE_PRICING_URL,
            _tier("0.10", "0.40", "0.01"),
        ),
    }
)

_PROVIDER_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "anthropic": "anthropic",
        "claude": "anthropic",
        "google": "google",
        "google ai": "google",
        "google-ai": "google",
        "googleai": "google",
        "gemini": "google",
        "openai": "openai",
        "open ai": "openai",
        "open-ai": "openai",
    }
)

_MODEL_ALIASES: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("anthropic", "claude 4 7 opus"): "claude-opus-4.7",
        ("anthropic", "claude 4.7 opus"): "claude-opus-4.7",
        ("anthropic", "claude-4-7-opus"): "claude-opus-4.7",
        ("anthropic", "claude-opus-4-7"): "claude-opus-4.7",
        ("anthropic", "claude opus 4.7"): "claude-opus-4.7",
        ("anthropic", "claude-opus-4-6"): "claude-opus-4.6",
        ("anthropic", "claude-opus-4-5"): "claude-opus-4.5",
        ("anthropic", "claude-opus-4-1"): "claude-opus-4.1",
        ("anthropic", "claude-sonnet-4-6"): "claude-sonnet-4.6",
        ("anthropic", "claude sonnet 4.5"): "claude-sonnet-4.5",
        ("anthropic", "claude-sonnet-4-5"): "claude-sonnet-4.5",
        ("anthropic", "claude-sonnet-3-7"): "claude-sonnet-3.7",
        ("anthropic", "claude-haiku-4-5"): "claude-haiku-4.5",
        ("anthropic", "claude-haiku-4-5-20251001"): "claude-haiku-4.5",
        ("anthropic", "claude-haiku-3-5"): "claude-haiku-3.5",
        ("google", "gemini 2.5 pro preview"): "gemini-2.5-pro",
        ("openai", "gpt 5.4 mini"): "gpt-5.4-mini",
    }
)


def normalize_provider(provider: str) -> str | None:
    """Return the canonical provider key for a known provider alias."""
    normalized = " ".join(provider.strip().lower().replace("_", "-").split())
    return _PROVIDER_ALIASES.get(normalized)


def normalize_model(provider: str, model: str) -> str | None:
    """Return the canonical model key for a known provider/model alias."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider is None:
        return None

    normalized_model = " ".join(model.strip().lower().replace("_", "-").split())
    alias = _MODEL_ALIASES.get((normalized_provider, normalized_model))
    if alias is not None:
        return alias

    catalog_key = normalized_model
    if (normalized_provider, catalog_key) in MODEL_PRICES:
        return catalog_key
    return None


def lookup_model_price(provider: str, model: str) -> ModelPrice | None:
    """Find an immutable catalog entry for a provider/model pair."""
    normalized_provider = normalize_provider(provider)
    if normalized_provider is None:
        return None

    normalized_model = normalize_model(normalized_provider, model)
    if normalized_model is None:
        return None

    return MODEL_PRICES.get((normalized_provider, normalized_model))


def compute_cost(usage: Usage | None, model: str, provider: str) -> CostBreakdown | None:
    """Compute a rounded USD cost breakdown from canonical token usage."""
    if usage is None:
        return None

    price = lookup_model_price(provider, model)
    if price is None:
        return None

    total_input_tokens = usage.input_tokens or 0
    cached_input_tokens = min(usage.cached_input_tokens or 0, total_input_tokens)
    output_tokens = usage.output_tokens or 0
    if total_input_tokens <= 0 and output_tokens <= 0:
        return None

    tier = _select_tier(price, total_input_tokens)
    if tier.cached_input_usd_per_1m is None:
        billable_input_tokens = total_input_tokens
        billable_cached_input_tokens = 0
    else:
        billable_cached_input_tokens = cached_input_tokens
        billable_input_tokens = max(total_input_tokens - cached_input_tokens, 0)

    input_cost = _round_usd(_token_cost(billable_input_tokens, tier.input_usd_per_1m))
    cached_input_cost = _round_usd(
        _token_cost(billable_cached_input_tokens, tier.cached_input_usd_per_1m or Decimal("0"))
    )
    output_cost = _round_usd(_token_cost(output_tokens, tier.output_usd_per_1m))
    total_cost = _round_usd(input_cost + cached_input_cost + output_cost)

    return CostBreakdown(
        provider=price.provider,
        model=price.model,
        input_tokens=billable_input_tokens,
        cached_input_tokens=billable_cached_input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
    )


def _select_tier(price: ModelPrice, input_tokens: int) -> PriceTier:
    for tier in price.tiers:
        if tier.max_input_tokens is None or input_tokens <= tier.max_input_tokens:
            return tier
    return price.tiers[-1]


def _token_cost(tokens: int, usd_per_1m: Decimal) -> Decimal:
    return (Decimal(tokens) * usd_per_1m) / _TOKENS_PER_MILLION


def _round_usd(value: Decimal) -> Decimal:
    return value.quantize(_USD_QUANTUM)


__all__ = [
    "PRICE_CATALOG_SNAPSHOT_DATE",
    "MODEL_PRICES",
    "CostBreakdown",
    "ModelPrice",
    "PriceTier",
    "compute_cost",
    "lookup_model_price",
    "normalize_model",
    "normalize_provider",
]
