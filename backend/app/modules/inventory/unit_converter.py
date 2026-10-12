"""Smart Unit Conversion Engine for Hardware Retail.

Rules & Invariants (per Section 3.1 & Module 2 of Development Plan):
1. Every product has exactly one atomic base unit (piece, kg, metre, sqft, litre).
2. Packaging units define a conversion factor to base unit (e.g. 1 Box = 100 pcs, 1 Coil = 90 m).
3. Stock is strictly tracked in base units with 4 decimal places (NUMERIC(18, 4)).
4. Variable-weight items (TMT rods, angles, sheets):
   The unit has a standard conversion factor (e.g. 1 rod 12mm ≈ 10.65 kg),
   but clerks can enter actual weighed kg, moving stock by actual weight.
5. Mixed unit decomposition (e.g. 963 pcs -> '9 Box 63 piece (963 piece)').
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field


class UnitDefinition(BaseModel):
    unit_name: str
    conversion_factor: Decimal = Field(gt=0, description="Factor to multiply to get base unit")
    can_buy: bool = True
    can_sell: bool = True
    barcode: Optional[str] = None
    is_default_sales_unit: bool = False
    is_default_purchase_unit: bool = False


class SmartUnitConverter:
    @staticmethod
    def resolve_conversion_factor(units, unit_name: str, fallback: Decimal) -> Decimal:
        """Return the catalogue conversion factor for unit_name (case-insensitive).

        The product master is authoritative: a client-supplied factor is only used
        when the unit is not defined on the product.
        """
        wanted = (unit_name or "").strip().lower()
        for u in units or []:
            if u.unit_name.strip().lower() == wanted:
                return Decimal(u.conversion_factor)
        return fallback

    @staticmethod
    def to_base_quantity(
        quantity: Decimal,
        unit: UnitDefinition,
        is_variable_weight: bool = False,
        actual_weight_kg: Optional[Decimal] = None,
    ) -> Decimal:
        """Convert a transaction quantity to base unit quantity.
        
        If variable-weight item and actual_weight_kg is supplied, actual weight
        overrides the nominal conversion factor.
        """
        if is_variable_weight and actual_weight_kg is not None:
            return actual_weight_kg.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        base_qty = quantity * unit.conversion_factor
        return base_qty.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def to_display_units(
        total_base_qty: Decimal,
        base_unit: str,
        packaging_units: List[UnitDefinition],
    ) -> str:
        """Decompose atomic base quantity into hierarchical packaging units.
        
        Example: 963 pieces with Box = 100 pcs -> "9 Box 63 piece (963 piece)"
        """
        # Sort packaging units descending by conversion factor (> 1.0)
        sorted_units = sorted(
            [u for u in packaging_units if u.conversion_factor > Decimal("1.0")],
            key=lambda u: u.conversion_factor,
            reverse=True,
        )

        remaining = total_base_qty
        parts: List[str] = []

        for unit in sorted_units:
            count = int(remaining // unit.conversion_factor)
            if count > 0:
                parts.append(f"{count} {unit.unit_name}")
                remaining = remaining % unit.conversion_factor

        # Append remaining base units if any or if parts is empty
        normalized_rem = remaining.normalize()
        if remaining > 0 or not parts:
            # Format cleanly (avoid .0000 if whole number)
            rem_str = f"{normalized_rem:f}" if normalized_rem % 1 else f"{int(normalized_rem)}"
            parts.append(f"{rem_str} {base_unit}")

        base_summary = f"{total_base_qty.normalize():f}" if total_base_qty % 1 else f"{int(total_base_qty)}"
        return f"{' '.join(parts)} ({base_summary} {base_unit})"

    @staticmethod
    def calculate_weighted_average_cost(
        current_base_qty: Decimal,
        current_wac_base: Decimal,
        inward_base_qty: Decimal,
        inward_landed_cost_base: Decimal,
    ) -> Decimal:
        """Recalculate Weighted Average Cost on inward stock movement.
        
        Formula:
        WAC_new = ((current_qty * current_wac) + (inward_qty * inward_cost)) / (current_qty + inward_qty)
        If current stock is zero or negative, WAC is set directly to inward_cost.
        """
        if current_base_qty <= Decimal("0"):
            return inward_landed_cost_base.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        total_qty = current_base_qty + inward_base_qty
        if total_qty <= Decimal("0"):
            return inward_landed_cost_base.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        total_value = (current_base_qty * current_wac_base) + (inward_base_qty * inward_landed_cost_base)
        new_wac = total_value / total_qty
        return new_wac.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
