"""Deterministic Procurement Cost & Quote Arithmetic Calculator."""

from typing import Any, Dict


def calculate_delivered_cost(
    commodity: str,
    base_price_rs_qtl: float,
    freight_per_tonne: float,
    ancillary_per_tonne: float = 0.0,
    order_tonnes: float = 100.0,
    is_pod: bool = False,
    decortication_allowance_tonne: float = 1500.0,
) -> Dict[str, Any]:
    """Calculate delivered landed procurement cost per tonne and order total.

    Parameters:
    - commodity: Name of the commodity ('Groundnut', 'Soybean', 'Mustard')
    - base_price_rs_qtl: Wholesale price in INR per quintal (1 Quintal = 100 kg)
    - freight_per_tonne: Transportation and logistics cost per metric tonne
    - ancillary_per_tonne: Mandi cess, loading, unloading, brokerage, and weighment charges
    - order_tonnes: Procurement volume requirement in metric tonnes (e.g. 100 MT)
    - is_pod: Applicable to Groundnut; whether quotation is for unshelled pods vs kernels
    - decortication_allowance_tonne: Processing allowance to decorticate pods to kernels (benchmark ₹1,500/MT)
    """
    raw_seed_cost_per_tonne = base_price_rs_qtl * 10.0

    if is_pod and commodity.lower() == "groundnut":
        # Groundnut pod-to-kernel conversion: 70% Shelling Outturn benchmark
        shelling_outturn = 0.70
        effective_kernel_cost_tonne = (raw_seed_cost_per_tonne / shelling_outturn) + decortication_allowance_tonne
        landed_cost_per_tonne = effective_kernel_cost_tonne + freight_per_tonne + ancillary_per_tonne
        valuation_basis = "Kernel Equivalent Benchmark (70% Shelling Outturn)"
    else:
        effective_kernel_cost_tonne = raw_seed_cost_per_tonne
        landed_cost_per_tonne = raw_seed_cost_per_tonne + freight_per_tonne + ancillary_per_tonne
        valuation_basis = "Whole Seed Delivered Cost Basis"

    total_order_cost = landed_cost_per_tonne * order_tonnes

    return {
        "commodity": commodity,
        "input_price_rs_qtl": round(base_price_rs_qtl, 2),
        "raw_price_per_tonne": round(raw_seed_cost_per_tonne, 2),
        "valuation_basis": valuation_basis,
        "effective_material_cost_per_tonne": round(effective_kernel_cost_tonne, 2),
        "freight_per_tonne": round(freight_per_tonne, 2),
        "ancillary_per_tonne": round(ancillary_per_tonne, 2),
        "delivered_cost_per_tonne": round(landed_cost_per_tonne, 2),
        "order_volume_tonnes": round(order_tonnes, 2),
        "total_delivered_cost_inr": round(total_order_cost, 2),
    }
