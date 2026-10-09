"""Sprint 0 Spike Demo — Unit Conversion + Offline Bill + Thermal Receipt.

Run this script to see a full end-to-end simulation:
1. Import a mini hardware product catalogue with smart unit conversions.
2. Process a 5-line POS cash bill with mixed units, GST splits, and discount.
3. Print a formatted 3-inch thermal receipt with dynamic UPI QR code.
4. Show mixed-unit stock decomposition after the sale.

Usage:
    python backend/app/spike_demo.py
"""

import sys
import os
import io

# Fix Windows console encoding for Unicode/emoji output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from decimal import Decimal
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition
from app.modules.billing.invoice_calculator import InvoiceCalculator, InvoiceLineInput, DiscountType
from app.modules.billing.thermal_printer import ThermalReceiptGenerator, ShopProfile


def main():
    print("=" * 60)
    print("  Hardware Billing OS — Sprint 0 Spike Demo")
    print("  Unit Conversion + Offline Bill + Thermal Receipt")
    print("=" * 60)

    # ── 1. Product Catalogue with Smart Units ───────────────────
    print("\n📦 PRODUCT CATALOGUE (with unit conversions)")
    print("-" * 60)

    catalogue = [
        {
            "name": "SS Self-Tapping Screws 25mm",
            "base_unit": "piece",
            "units": [UnitDefinition(unit_name="Box", conversion_factor=Decimal("100"))],
            "stock_base": Decimal("5000"),
        },
        {
            "name": "TMT 12mm Fe500D Rod",
            "base_unit": "kg",
            "units": [UnitDefinition(unit_name="Rod", conversion_factor=Decimal("10.65"))],
            "stock_base": Decimal("2130"),  # ~200 rods
            "is_variable_weight": True,
        },
        {
            "name": "Asian Tractor Emulsion 1L",
            "base_unit": "piece",
            "units": [UnitDefinition(unit_name="Case", conversion_factor=Decimal("12"))],
            "stock_base": Decimal("120"),
        },
        {
            "name": "CPVC Pipe 1\" Ashirvad",
            "base_unit": "piece",
            "units": [],
            "stock_base": Decimal("340"),
        },
        {
            "name": "GI Binding Wire 20 gauge",
            "base_unit": "kg",
            "units": [UnitDefinition(unit_name="Coil", conversion_factor=Decimal("25"))],
            "stock_base": Decimal("500"),
        },
    ]

    for p in catalogue:
        display = SmartUnitConverter.to_display_units(
            p["stock_base"], p["base_unit"], p.get("units", [])
        )
        print(f"  {p['name']:<35} Stock: {display}")

    # ── 2. Create a 5-Line POS Bill ─────────────────────────────
    print("\n\n🧾 POS BILLING — 5-Line Cash Bill (Contractor Price List)")
    print("-" * 60)

    bill_lines = [
        InvoiceLineInput(
            product_id="p1", product_code="SCR001",
            product_name="SS Screws 25mm", tamil_name="எஃகு திருகு",
            unit_name="Box", conversion_factor=Decimal("100"),
            quantity=Decimal("3"), unit_price=Decimal("185"),
            hsn_code="7318", gst_rate_percent=Decimal("18"),
        ),
        InvoiceLineInput(
            product_id="p2", product_code="TMT001",
            product_name="TMT 12mm Fe500D", tamil_name="TMT கம்பி",
            unit_name="Rod", conversion_factor=Decimal("10.65"),
            quantity=Decimal("10"), unit_price=Decimal("650"),
            is_variable_weight=True, actual_weight_kg=Decimal("104.2"),
            hsn_code="7214", gst_rate_percent=Decimal("18"),
        ),
        InvoiceLineInput(
            product_id="p3", product_code="PNT001",
            product_name="Asian Emulsion 1L", tamil_name="பெயிண்ட்",
            unit_name="piece", conversion_factor=Decimal("1"),
            quantity=Decimal("6"), unit_price=Decimal("275"),
            discount_type=DiscountType.PERCENT, discount_value=Decimal("5"),
            hsn_code="3208", gst_rate_percent=Decimal("18"),
        ),
        InvoiceLineInput(
            product_id="p4", product_code="PIP001",
            product_name="CPVC Pipe 1\" Ashirvad", tamil_name="CPVC குழாய்",
            unit_name="piece", conversion_factor=Decimal("1"),
            quantity=Decimal("20"), unit_price=Decimal("85"),
            hsn_code="3917", gst_rate_percent=Decimal("18"),
        ),
        InvoiceLineInput(
            product_id="p5", product_code="GIW001",
            product_name="GI Wire 20ga", tamil_name="கட்டு கம்பி",
            unit_name="Coil", conversion_factor=Decimal("25"),
            quantity=Decimal("2"), unit_price=Decimal("1850"),
            hsn_code="7217", gst_rate_percent=Decimal("18"),
        ),
    ]

    invoice = InvoiceCalculator.calculate_invoice(
        lines_input=bill_lines,
        tenant_state_code="33",
        place_of_supply_state_code="33",
        paid_amount=None,  # Full cash payment
    )

    print(f"  Lines:     {len(invoice.lines)}")
    print(f"  Subtotal:  ₹{invoice.subtotal_taxable:,.2f}")
    print(f"  CGST:      ₹{invoice.cgst_total:,.2f}")
    print(f"  SGST:      ₹{invoice.sgst_total:,.2f}")
    print(f"  Round-Off: ₹{invoice.round_off:+,.2f}")
    print(f"  Grand Tot: ₹{invoice.grand_total:,.2f}")
    print(f"  Type:      {'Inter-State (IGST)' if invoice.is_inter_state else 'Intra-State (CGST+SGST)'}")

    # ── 3. Thermal Receipt ──────────────────────────────────────
    print("\n\n🖨️  THERMAL RECEIPT (3-inch format)")
    print("=" * 48)

    shop = ShopProfile(
        business_name="SALEM TRADERS",
        trade_name="சேலம் வணிகர்கள்",
        gstin="33AABCT1234F1ZP",
        phone="98765 43210",
        address="123 Main Rd, Salem - 636001",
        upi_vpa="salemtraders@icici",
    )

    receipt = ThermalReceiptGenerator.format_text_receipt(
        shop=shop,
        invoice=invoice,
        invoice_number="C1/26-27/0001",
        invoice_date_str="09-Oct-2026 12:00",
        counter_code="COUNTER-1",
        customer_name="Murugan Const.",
        customer_phone="94422 11234",
    )
    print(receipt)

    # ── 4. Stock After Sale ─────────────────────────────────────
    print("\n\n📊 STOCK AFTER SALE (mixed unit display)")
    print("-" * 60)

    sale_deductions = {
        0: Decimal("300"),    # 3 boxes * 100 = 300 pcs
        1: Decimal("104.2"),  # actual weighed TMT
        2: Decimal("6"),      # 6 pcs paint
        3: Decimal("20"),     # 20 pcs pipe
        4: Decimal("50"),     # 2 coils * 25 = 50 kg
    }

    for idx, p in enumerate(catalogue):
        new_stock = p["stock_base"] - sale_deductions.get(idx, Decimal("0"))
        display = SmartUnitConverter.to_display_units(
            new_stock, p["base_unit"], p.get("units", [])
        )
        print(f"  {p['name']:<35} Stock: {display}")

    # ── 5. ESC/POS Byte Size ────────────────────────────────────
    escpos_bytes = ThermalReceiptGenerator.generate_escpos_bytes(receipt)
    print(f"\n\n📡 ESC/POS payload ready: {len(escpos_bytes)} bytes")
    print(f"   (Would be sent raw to USB/COM thermal printer)")

    print("\n" + "=" * 60)
    print("  ✅ Spike Demo Complete — All 3 pillars working:")
    print("     1. Smart Unit Conversion ✓")
    print("     2. GST Invoice Calculation ✓")
    print("     3. Thermal Receipt + UPI QR ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
