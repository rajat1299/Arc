from decimal import Decimal

import pytest
from opscanvas_core.events import Usage
from opscanvas_core.pricing import (
    MODEL_PRICES,
    PRICE_CATALOG_SNAPSHOT_DATE,
    CostBreakdown,
    compute_cost,
    lookup_model_price,
    normalize_model,
    normalize_provider,
)


def test_openai_cached_input_is_split_from_uncached_input() -> None:
    cost = compute_cost(
        Usage(input_tokens=1_000, cached_input_tokens=400, output_tokens=200),
        model="gpt-5.4",
        provider="openai",
    )

    assert cost == CostBreakdown(
        provider="openai",
        model="gpt-5.4",
        input_tokens=600,
        cached_input_tokens=400,
        output_tokens=200,
        input_cost_usd=Decimal("0.0015000000"),
        cached_input_cost_usd=Decimal("0.0001000000"),
        output_cost_usd=Decimal("0.0030000000"),
        total_cost_usd=Decimal("0.0046000000"),
    )


def test_anthropic_cached_input_pricing_uses_catalog_rate() -> None:
    cost = compute_cost(
        Usage(input_tokens=2_000, cached_input_tokens=1_500, output_tokens=300),
        model="Claude Sonnet 4.5",
        provider="Anthropic",
    )

    assert cost is not None
    assert cost.provider == "anthropic"
    assert cost.model == "claude-sonnet-4.5"
    assert cost.input_cost_usd == Decimal("0.0015000000")
    assert cost.cached_input_cost_usd == Decimal("0.0004500000")
    assert cost.output_cost_usd == Decimal("0.0045000000")
    assert cost.total_cost_usd == Decimal("0.0064500000")


@pytest.mark.parametrize(
    ("model", "canonical_model", "expected_total"),
    [
        ("claude-opus-4-7", "claude-opus-4.7", Decimal("0.0300000000")),
        ("claude-sonnet-4-6", "claude-sonnet-4.6", Decimal("0.0180000000")),
        ("claude-haiku-4-5-20251001", "claude-haiku-4.5", Decimal("0.0060000000")),
    ],
)
def test_anthropic_api_ids_resolve_to_catalog_prices(
    model: str,
    canonical_model: str,
    expected_total: Decimal,
) -> None:
    assert normalize_model("anthropic", model) == canonical_model
    assert lookup_model_price("anthropic", model) is not None

    cost = compute_cost(
        Usage(input_tokens=1_000, output_tokens=1_000),
        model=model,
        provider="anthropic",
    )

    assert cost is not None
    assert cost.model == canonical_model
    assert cost.total_cost_usd == expected_total


def test_gemini_25_pro_uses_short_context_tier_at_200k_input_tokens() -> None:
    cost = compute_cost(
        Usage(input_tokens=200_000, cached_input_tokens=50_000, output_tokens=1_000),
        model="gemini-2.5-pro",
        provider="google",
    )

    assert cost is not None
    assert cost.input_cost_usd == Decimal("0.1875000000")
    assert cost.cached_input_cost_usd == Decimal("0.0062500000")
    assert cost.output_cost_usd == Decimal("0.0100000000")
    assert cost.total_cost_usd == Decimal("0.2037500000")


def test_gemini_25_pro_uses_long_context_tier_above_200k_input_tokens() -> None:
    cost = compute_cost(
        Usage(input_tokens=200_001, cached_input_tokens=50_000, output_tokens=1_000),
        model="gemini-2.5-pro",
        provider="google",
    )

    assert cost is not None
    assert cost.input_cost_usd == Decimal("0.3750025000")
    assert cost.cached_input_cost_usd == Decimal("0.0125000000")
    assert cost.output_cost_usd == Decimal("0.0150000000")
    assert cost.total_cost_usd == Decimal("0.4025025000")


def test_provider_and_model_aliases_normalize_to_catalog_keys() -> None:
    assert PRICE_CATALOG_SNAPSHOT_DATE == "2026-04-27"
    assert normalize_provider("Google AI") == "google"
    assert normalize_provider("Gemini") == "google"
    assert normalize_model("openai", "GPT 5.4 Mini") == "gpt-5.4-mini"
    assert normalize_model("anthropic", "claude-4-7-opus") == "claude-opus-4.7"
    assert normalize_model("google", "Gemini 2.5 Pro Preview") == "gemini-2.5-pro"
    assert lookup_model_price("Google AI", "Gemini 2.5 Pro Preview") is not None


def test_unknown_model_returns_none() -> None:
    assert lookup_model_price("openai", "gpt-does-not-exist") is None
    assert (
        compute_cost(Usage(input_tokens=1_000), model="gpt-does-not-exist", provider="openai")
        is None
    )


def test_missing_usage_or_no_billable_usage_returns_none() -> None:
    assert compute_cost(None, model="gpt-5.4", provider="openai") is None
    assert compute_cost(Usage(total_tokens=1_000), model="gpt-5.4", provider="openai") is None
    assert (
        compute_cost(
            Usage(input_tokens=0, cached_input_tokens=0, output_tokens=0),
            model="gpt-5.4",
            provider="openai",
        )
        is None
    )


def test_cached_input_tokens_are_clamped_to_total_input_tokens() -> None:
    cost = compute_cost(
        Usage(input_tokens=100, cached_input_tokens=200, output_tokens=0),
        model="gpt-5.4",
        provider="openai",
    )

    assert cost is not None
    assert cost.input_tokens == 0
    assert cost.cached_input_tokens == 100
    assert cost.input_cost_usd == Decimal("0.0000000000")
    assert cost.cached_input_cost_usd == Decimal("0.0000250000")
    assert cost.total_cost_usd == Decimal("0.0000250000")


def test_rounding_is_deterministic_to_ten_decimal_places() -> None:
    cost = compute_cost(Usage(input_tokens=1), model="gpt-5.5", provider="openai")

    assert cost is not None
    assert cost.total_cost_usd == Decimal("0.0000050000")
    assert cost.total_cost_usd.as_tuple().exponent == -10


def test_catalog_entries_include_source_urls() -> None:
    assert MODEL_PRICES
    assert all(price.source_url.startswith("https://") for price in MODEL_PRICES.values())


def test_pricing_symbols_are_exported_from_package_root() -> None:
    import opscanvas_core

    assert opscanvas_core.PRICE_CATALOG_SNAPSHOT_DATE == PRICE_CATALOG_SNAPSHOT_DATE
    assert opscanvas_core.MODEL_PRICES is MODEL_PRICES
    assert opscanvas_core.normalize_provider is normalize_provider
    assert opscanvas_core.normalize_model is normalize_model
    assert opscanvas_core.lookup_model_price is lookup_model_price
    assert opscanvas_core.compute_cost is compute_cost
