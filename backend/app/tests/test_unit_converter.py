"""Golden-file tests for Smart Unit Conversion Engine.

These tests verify the core invariants from Section 3.1 of the Development Plan:
1. Base unit quantity is always correct to 4 decimal places.
2. Mixed-unit decomposition displays human-readable packaging.
3. Variable-weight items use actual weight instead of nominal conversion.
4. Weighted Average Cost recalculates correctly on inward stock.
"""

import pytest
from decimal import Decimal

from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition


# ─── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def screw_box_unit():
    """Box = 100 pieces."""
    return UnitDefinition(
        unit_name="Box",
        conversion_factor=Decimal("100"),
        can_buy=True,
        can_sell=True,
        is_default_purchase_unit=True,
    )


@pytest.fixture
def wire_coil_unit():
    """Coil = 90 metres."""
    return UnitDefinition(
        unit_name="Coil",
        conversion_factor=Decimal("90"),
        can_buy=True,
        can_sell=True,
    )


@pytest.fixture
def tmt_rod_unit():
    """Rod of 12mm TMT ≈ 10.65 kg standard weight."""
    return UnitDefinition(
        unit_name="Rod",
        conversion_factor=Decimal("10.65"),
        can_buy=True,
        can_sell=True,
    )


@pytest.fixture
def tile_box_unit():
    """Tile Box = 8 pcs = 15.5 sqft."""
    return UnitDefinition(
        unit_name="Box",
        conversion_factor=Decimal("8"),
        can_buy=True,
        can_sell=True,
    )


# ─── Test: Base Quantity Conversion ──────────────────────────────────
class TestBaseQuantityConversion:
    def test_box_to_pieces(self, screw_box_unit):
        """Buy 10 boxes (100 pcs/box) -> 1000 pcs base."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("10"),
            unit=screw_box_unit,
        )
        assert result == Decimal("1000.0000")

    def test_coil_to_metres(self, wire_coil_unit):
        """Buy 3 coils (90 m/coil) -> 270 metres base."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("3"),
            unit=wire_coil_unit,
        )
        assert result == Decimal("270.0000")

    def test_fractional_quantity(self, screw_box_unit):
        """Buy 2.5 boxes -> 250 pcs."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("2.5"),
            unit=screw_box_unit,
        )
        assert result == Decimal("250.0000")

    def test_single_piece_identity(self):
        """Selling 1 piece of base unit -> 1 piece."""
        piece = UnitDefinition(unit_name="piece", conversion_factor=Decimal("1"))
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("37"),
            unit=piece,
        )
        assert result == Decimal("37.0000")


# ─── Test: Variable Weight Override ─────────────────────────────────
class TestVariableWeight:
    def test_tmt_rod_with_actual_weight(self, tmt_rod_unit):
        """10 rods of 12mm TMT, but actual weight is 104.2 kg (not 106.5 kg)."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("10"),
            unit=tmt_rod_unit,
            is_variable_weight=True,
            actual_weight_kg=Decimal("104.2"),
        )
        assert result == Decimal("104.2000")

    def test_tmt_rod_without_actual_weight_uses_factor(self, tmt_rod_unit):
        """If actual weight not entered, use nominal factor: 10 rods * 10.65 = 106.5 kg."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("10"),
            unit=tmt_rod_unit,
            is_variable_weight=True,
            actual_weight_kg=None,
        )
        assert result == Decimal("106.5000")

    def test_non_variable_weight_ignores_actual(self, screw_box_unit):
        """Non-variable weight items always use conversion factor."""
        result = SmartUnitConverter.to_base_quantity(
            quantity=Decimal("5"),
            unit=screw_box_unit,
            is_variable_weight=False,
            actual_weight_kg=Decimal("999"),
        )
        assert result == Decimal("500.0000")


# ─── Test: Mixed Unit Decomposition ─────────────────────────────────
class TestMixedUnitDecomposition:
    def test_963_pieces_with_box(self, screw_box_unit):
        """963 pcs with Box=100 -> '9 Box 63 piece (963 piece)'."""
        result = SmartUnitConverter.to_display_units(
            total_base_qty=Decimal("963"),
            base_unit="piece",
            packaging_units=[screw_box_unit],
        )
        assert result == "9 Box 63 piece (963 piece)"

    def test_1000_pieces_exact_boxes(self, screw_box_unit):
        """Exactly 10 boxes = 1000 pcs -> '10 Box (1000 piece)'."""
        result = SmartUnitConverter.to_display_units(
            total_base_qty=Decimal("1000"),
            base_unit="piece",
            packaging_units=[screw_box_unit],
        )
        assert result == "10 Box (1000 piece)"

    def test_zero_stock(self, screw_box_unit):
        """Zero stock displays cleanly."""
        result = SmartUnitConverter.to_display_units(
            total_base_qty=Decimal("0"),
            base_unit="piece",
            packaging_units=[screw_box_unit],
        )
        assert result == "0 piece (0 piece)"

    def test_fractional_base_units(self):
        """23.75 kg of loose item."""
        result = SmartUnitConverter.to_display_units(
            total_base_qty=Decimal("23.75"),
            base_unit="kg",
            packaging_units=[],
        )
        assert result == "23.75 kg (23.75 kg)"

    def test_multi_tier_packaging(self):
        """Pallet = 10 boxes, Box = 100 pcs; 1263 pcs = 1 Pallet 2 Box 63 piece."""
        pallet = UnitDefinition(unit_name="Pallet", conversion_factor=Decimal("1000"))
        box = UnitDefinition(unit_name="Box", conversion_factor=Decimal("100"))

        result = SmartUnitConverter.to_display_units(
            total_base_qty=Decimal("1263"),
            base_unit="piece",
            packaging_units=[box, pallet],
        )
        assert result == "1 Pallet 2 Box 63 piece (1263 piece)"


# ─── Test: Weighted Average Cost ────────────────────────────────────
class TestWeightedAverageCost:
    def test_basic_wac_recalculation(self):
        """10 pcs @ ₹100, inward 10 pcs @ ₹120 -> new WAC = ₹110."""
        new_wac = SmartUnitConverter.calculate_weighted_average_cost(
            current_base_qty=Decimal("10"),
            current_wac_base=Decimal("100"),
            inward_base_qty=Decimal("10"),
            inward_landed_cost_base=Decimal("120"),
        )
        assert new_wac == Decimal("110.0000")

    def test_wac_with_zero_current_stock(self):
        """Zero current stock -> WAC = inward cost directly."""
        new_wac = SmartUnitConverter.calculate_weighted_average_cost(
            current_base_qty=Decimal("0"),
            current_wac_base=Decimal("0"),
            inward_base_qty=Decimal("50"),
            inward_landed_cost_base=Decimal("85.50"),
        )
        assert new_wac == Decimal("85.5000")

    def test_wac_with_negative_current_stock(self):
        """Negative current stock (pre-billed before purchase) -> WAC = inward cost."""
        new_wac = SmartUnitConverter.calculate_weighted_average_cost(
            current_base_qty=Decimal("-5"),
            current_wac_base=Decimal("90"),
            inward_base_qty=Decimal("100"),
            inward_landed_cost_base=Decimal("95"),
        )
        assert new_wac == Decimal("95.0000")

    def test_wac_asymmetric_quantities(self):
        """100 pcs @ ₹50, inward 25 pcs @ ₹60 -> WAC = (5000 + 1500) / 125 = 52.0000."""
        new_wac = SmartUnitConverter.calculate_weighted_average_cost(
            current_base_qty=Decimal("100"),
            current_wac_base=Decimal("50"),
            inward_base_qty=Decimal("25"),
            inward_landed_cost_base=Decimal("60"),
        )
        assert new_wac == Decimal("52.0000")

    def test_wac_with_freight_absorbed_cost(self):
        """Landed cost includes freight: 10 bags @ ₹400 + ₹200 freight = ₹420/bag effective."""
        new_wac = SmartUnitConverter.calculate_weighted_average_cost(
            current_base_qty=Decimal("0"),
            current_wac_base=Decimal("0"),
            inward_base_qty=Decimal("10"),
            inward_landed_cost_base=Decimal("420"),
        )
        assert new_wac == Decimal("420.0000")
