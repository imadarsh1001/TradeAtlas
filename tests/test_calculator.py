"""Delivered-cost arithmetic: whole-seed, pod conversion, rounding, envelope fields."""

from datetime import datetime

from tradeatlas.calculator import calculate_delivered_cost


def test_whole_seed_arithmetic():
    env = calculate_delivered_cost("Soybean", 5000, 500, 200)
    assert env.payload["delivered_cost_per_tonne"] == 50_700.00
    assert env.payload["valuation_basis"] == "Whole Seed Delivered Cost Basis"
    assert env.payload["total_delivered_cost_inr"] == 5_070_000.00  # 100 MT default


def test_pod_conversion_uses_70_percent_outturn():
    env = calculate_delivered_cost("Groundnut", 4000, 0, 0, is_pod=True)
    assert env.payload["effective_material_cost_per_tonne"] == 58_642.86
    assert env.payload["delivered_cost_per_tonne"] == 58_642.86
    assert env.payload["valuation_basis"] == "Kernel Equivalent Benchmark (70% Shelling Outturn)"


def test_pod_case_adds_freight_and_ancillary_on_kernel_cost():
    env = calculate_delivered_cost("Groundnut", 4000, 500, 200, is_pod=True)
    assert env.payload["delivered_cost_per_tonne"] == 59_342.86


def test_pod_case_carries_basis_caveat():
    env = calculate_delivered_cost("Groundnut", 4000, 500, 200, is_pod=True)
    assert any("70% shelling outturn" in c.lower() for c in env.caveats)
    env_seed = calculate_delivered_cost("Groundnut", 4000, 500, 200, is_pod=False)
    assert env_seed.caveats == []


def test_monetary_outputs_rounded_to_two_decimals():
    env = calculate_delivered_cost("Groundnut", 1234.567, 100.005, 0, is_pod=True)
    assert env.payload["effective_material_cost_per_tonne"] == round(12345.67 / 0.70 + 1500, 2)
    for key in (
        "input_price_rs_qtl",
        "effective_material_cost_per_tonne",
        "delivered_cost_per_tonne",
        "total_delivered_cost_inr",
    ):
        assert env.payload[key] == round(env.payload[key], 2)


def test_envelope_is_input_only_deep():
    env = calculate_delivered_cost("Groundnut", 4000, 500, 200, is_pod=True)
    assert env.tier == "deep"
    assert env.coverage == "user-supplied inputs"
    assert env.observation_dates == []
    # retrieved_at is timezone-aware UTC ISO-8601
    parsed = datetime.fromisoformat(env.retrieved_at)
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
