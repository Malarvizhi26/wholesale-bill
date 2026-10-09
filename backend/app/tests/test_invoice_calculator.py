"""Golden-file tests for POS Invoice Calculator.

These tests verify the core invariants from Section 3.3 of AGENTS.md:
1. Intra-state vs Inter-state GST splits.
2. Exact 2-decimal line rounding.
3. Round-off within [-0.49, +0.50].
4. Variable-weight base quantity on invoice lines.
"""

import pytest
from decimal import Decimal

from app.modules.billing.invoice_calculator import (
    InvoiceCalculator,
    InvoiceLineInput,
    DiscountType,
)


# ─── Intra-State (CGST + SGST) ──────────────────────────────────────
class TestIntraStateGST:
    def test_single_line_18_percent_gst(self):
        """1 item @ ₹1000, 18% GST intra-state -> CGST 90, SGST 90, total 1180."""
        lines = [
            InvoiceLineInput(
                product_id="p1",
                product_code="SCR001",
                product_name="SS Screws",
                unit_name="Box",
                conversion_factor=Decimal("100"),
                quantity=Decimal("1"),
                unit_price=Decimal("1000"),
                hsn_code="7318",
                gst_rate_percent=Decimal("18"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(
            lines_input=lines,
            tenant_state_code="33",
            place_of_supply_state_code="33",
        )

        assert result.is_inter_state is False
        line = result.lines[0]
        assert line.taxable_amount == Decimal("1000.00")
        assert line.cgst_percent == Decimal("9")
        assert line.cgst_amount == Decimal("90.00")
        assert line.sgst_percent == Decimal("9")
        assert line.sgst_amount == Decimal("90.00")
        assert line.igst_amount == Decimal("0.00")
        assert line.line_total == Decimal("1180.00")
        assert result.grand_total == Decimal("1180.00")
        assert result.round_off == Decimal("0.00")

    def test_5_line_cash_bill_intra_state(self):
        """Simulates a 5-line POS bill with mixed GST rates, verifying totals."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="CEM001", product_name="Cement 50kg",
                unit_name="Bag", conversion_factor=Decimal("1"),
                quantity=Decimal("10"), unit_price=Decimal("400"),
                hsn_code="2523", gst_rate_percent=Decimal("28"),
            ),
            InvoiceLineInput(
                product_id="p2", product_code="TMT001", product_name="TMT 12mm Rod",
                unit_name="Rod", conversion_factor=Decimal("10.65"),
                quantity=Decimal("5"), unit_price=Decimal("650"),
                is_variable_weight=True, actual_weight_kg=Decimal("52.8"),
                hsn_code="7214", gst_rate_percent=Decimal("18"),
            ),
            InvoiceLineInput(
                product_id="p3", product_code="PNT001", product_name="Asian Primer 1L",
                unit_name="Tin", conversion_factor=Decimal("1"),
                quantity=Decimal("4"), unit_price=Decimal("275"),
                hsn_code="3208", gst_rate_percent=Decimal("18"),
            ),
            InvoiceLineInput(
                product_id="p4", product_code="PIP001", product_name="CPVC Pipe 1 inch",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("20"), unit_price=Decimal("85"),
                hsn_code="3917", gst_rate_percent=Decimal("18"),
            ),
            InvoiceLineInput(
                product_id="p5", product_code="SND001", product_name="River Sand",
                unit_name="CFT", conversion_factor=Decimal("1"),
                quantity=Decimal("100"), unit_price=Decimal("45"),
                hsn_code="2505", gst_rate_percent=Decimal("5"),
            ),
        ]
        result = InvoiceCalculator.calculate_invoice(
            lines_input=lines,
            tenant_state_code="33",
            place_of_supply_state_code="33",
        )

        assert result.is_inter_state is False
        assert len(result.lines) == 5

        # TMT rod should use actual weight 52.8 kg as base_quantity
        tmt_line = result.lines[1]
        assert tmt_line.base_quantity == Decimal("52.8000")

        # Verify grand total is rounded to nearest rupee
        assert result.grand_total == result.grand_total.quantize(Decimal("1.00"))

        # Round-off must be within [-0.49, +0.50]
        assert Decimal("-0.50") < result.round_off <= Decimal("0.50")

        # All individual GST amounts should be non-negative
        for line in result.lines:
            assert line.cgst_amount >= 0
            assert line.sgst_amount >= 0
            assert line.igst_amount == Decimal("0.00")


# ─── Inter-State (IGST) ─────────────────────────────────────────────
class TestInterStateGST:
    def test_single_line_igst(self):
        """Inter-state sale: shop in TN (33), customer in KA (29) -> full IGST."""
        lines = [
            InvoiceLineInput(
                product_id="p1",
                product_code="CEM001",
                product_name="Cement 50kg",
                unit_name="Bag",
                conversion_factor=Decimal("1"),
                quantity=Decimal("100"),
                unit_price=Decimal("400"),
                hsn_code="2523",
                gst_rate_percent=Decimal("28"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(
            lines_input=lines,
            tenant_state_code="33",
            place_of_supply_state_code="29",
        )

        assert result.is_inter_state is True
        line = result.lines[0]
        assert line.igst_percent == Decimal("28")
        assert line.igst_amount == Decimal("11200.00")
        assert line.cgst_amount == Decimal("0.00")
        assert line.sgst_amount == Decimal("0.00")
        assert result.igst_total == Decimal("11200.00")
        assert result.cgst_total == Decimal("0.00")
        assert result.sgst_total == Decimal("0.00")


# ─── Discounts ───────────────────────────────────────────────────────
class TestDiscounts:
    def test_flat_discount(self):
        """₹50 flat discount on ₹1000 item -> taxable = ₹950."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="X001", product_name="Item X",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("1"), unit_price=Decimal("1000"),
                discount_type=DiscountType.FLAT, discount_value=Decimal("50"),
                hsn_code="8544", gst_rate_percent=Decimal("18"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(lines_input=lines)
        assert result.lines[0].taxable_amount == Decimal("950.00")
        assert result.lines[0].discount_amount == Decimal("50.00")

    def test_percent_discount(self):
        """10% discount on ₹2000 -> discount ₹200, taxable ₹1800."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="Y001", product_name="Item Y",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("2"), unit_price=Decimal("1000"),
                discount_type=DiscountType.PERCENT, discount_value=Decimal("10"),
                hsn_code="8544", gst_rate_percent=Decimal("18"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(lines_input=lines)
        assert result.lines[0].discount_amount == Decimal("200.00")
        assert result.lines[0].taxable_amount == Decimal("1800.00")


# ─── Round-Off ───────────────────────────────────────────────────────
class TestRoundOff:
    def test_round_off_within_bounds(self):
        """Verify round-off is always within [-0.49, +0.50] for odd-paisa totals."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="Z001", product_name="Odd Price Item",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("3"), unit_price=Decimal("33.33"),
                hsn_code="3926", gst_rate_percent=Decimal("12"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(lines_input=lines)
        assert Decimal("-0.50") < result.round_off <= Decimal("0.50")
        # Grand total must be a whole rupee
        assert result.grand_total == result.grand_total.quantize(Decimal("1.00"))


# ─── Credit & Due Amount ────────────────────────────────────────────
class TestPaymentDue:
    def test_full_payment_no_due(self):
        """Paid in full -> due = 0 (default behavior when paid_amount is not passed)."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="A001", product_name="Item A",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("1"), unit_price=Decimal("500"),
                hsn_code="7318", gst_rate_percent=Decimal("18"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(lines_input=lines)
        assert result.due_amount == Decimal("0.00")
        assert result.paid_amount == result.grand_total

    def test_partial_payment_shows_due(self):
        """Partial payment of ₹200 on ₹590 bill -> due = ₹390."""
        lines = [
            InvoiceLineInput(
                product_id="p1", product_code="A001", product_name="Item A",
                unit_name="piece", conversion_factor=Decimal("1"),
                quantity=Decimal("1"), unit_price=Decimal("500"),
                hsn_code="7318", gst_rate_percent=Decimal("18"),
            )
        ]
        result = InvoiceCalculator.calculate_invoice(
            lines_input=lines,
            paid_amount=Decimal("200"),
        )
        assert result.due_amount == result.grand_total - Decimal("200")
        assert result.due_amount > Decimal("0.00")
