"""Thermal Receipt & Dynamic UPI QR Code Engine.

Generates:
1. Standard UPI QR payment intent strings (NPCI spec).
2. Clean ASCII/Unicode receipt formatting for terminal preview and log validation.
3. Raw ESC/POS command byte sequences for silent 2-inch and 3-inch thermal printing.
"""

from decimal import Decimal
import io
import urllib.parse
from typing import Optional
from pydantic import BaseModel
import qrcode

from app.modules.billing.invoice_calculator import CalculatedInvoice


class ShopProfile(BaseModel):
    business_name: str
    trade_name: Optional[str] = None
    gstin: Optional[str] = None
    phone: str
    address: str
    upi_vpa: str  # e.g. "9876543210@upi" or "salemtraders@icici"


class ThermalReceiptGenerator:
    @staticmethod
    def generate_upi_qr_string(
        vpa: str,
        payee_name: str,
        amount: Decimal,
        invoice_number: str,
    ) -> str:
        """Construct standard NPCI UPI payment intent URI."""
        params = {
            "pa": vpa,
            "pn": payee_name,
            "am": f"{amount:.2f}",
            "cu": "INR",
            "tn": f"Invoice {invoice_number}",
        }
        query_string = urllib.parse.urlencode(params)
        return f"upi://pay?{query_string}"

    @staticmethod
    def generate_upi_qr_ascii(upi_uri: str) -> str:
        """Render a compact ASCII QR code suitable for terminal inspection."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(upi_uri)
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f)
        f.seek(0)
        return f.read()

    @staticmethod
    def format_text_receipt(
        shop: ShopProfile,
        invoice: CalculatedInvoice,
        invoice_number: str,
        invoice_date_str: str,
        counter_code: str = "COUNTER-1",
        customer_name: str = "Walk-in Customer",
        customer_phone: Optional[str] = None,
        width: int = 48,  # 48 chars for 3-inch, 32 chars for 2-inch
    ) -> str:
        """Format an exact text receipt matching the 3-inch/2-inch thermal layout."""
        lines = []

        def center(text: str) -> str:
            return text.center(width)

        def row(left: str, right: str) -> str:
            space = width - len(left) - len(right)
            return left + " " * max(1, space) + right

        divider = "-" * width
        double_divider = "=" * width

        # 1. Header
        lines.append(center(shop.business_name))
        if shop.trade_name:
            lines.append(center(shop.trade_name))
        lines.append(center(shop.address))
        lines.append(center(f"Ph: {shop.phone}"))
        if shop.gstin:
            lines.append(center(f"GSTIN: {shop.gstin}"))
        lines.append(double_divider)

        # 2. Invoice Details
        lines.append(row(f"Bill: {invoice_number}", invoice_date_str))
        lines.append(row(f"Node: {counter_code}", f"Cust: {customer_name[:18]}"))
        if customer_phone:
            lines.append(f"Phone: {customer_phone}")
        lines.append(divider)

        # 3. Item Lines
        # Columns: Item (22) | Qty Unit (12) | Rate (6) | Total (8)
        lines.append(f"{'Item':<22}{'Qty':<10}{'Rate':>6}{'Total':>10}")
        lines.append(divider)

        for line in invoice.lines:
            name_display = line.product_name[:20]
            qty_unit = f"{line.quantity} {line.unit_name}"[:9]
            rate = f"{line.unit_price:.1f}"
            tot = f"{line.line_total:.2f}"
            lines.append(f"{name_display:<22}{qty_unit:<10}{rate:>6}{tot:>10}")
            if line.tamil_name:
                lines.append(f"  {line.tamil_name}")
            if line.discount_amount > 0:
                lines.append(f"  (Disc: -₹{line.discount_amount:.2f})")

        lines.append(divider)

        # 4. Totals & GST Summary
        lines.append(row("Taxable Subtotal:", f"Rs. {invoice.subtotal_taxable:.2f}"))
        if not invoice.is_inter_state:
            lines.append(row("CGST Total:", f"Rs. {invoice.cgst_total:.2f}"))
            lines.append(row("SGST Total:", f"Rs. {invoice.sgst_total:.2f}"))
        else:
            lines.append(row("IGST Total:", f"Rs. {invoice.igst_total:.2f}"))

        if invoice.total_discount > 0:
            lines.append(row("Total Savings:", f"Rs. {invoice.total_discount:.2f}"))
        if invoice.round_off != Decimal("0.00"):
            lines.append(row("Round Off:", f"{invoice.round_off:+.2f}"))

        lines.append(double_divider)
        lines.append(row("NET TOTAL:", f"Rs. {invoice.grand_total:.2f}"))
        lines.append(double_divider)

        lines.append(row("Paid Amount:", f"Rs. {invoice.paid_amount:.2f}"))
        if invoice.due_amount > 0:
            lines.append(row("Balance Due:", f"Rs. {invoice.due_amount:.2f}"))

        lines.append(divider)

        # 5. Dynamic UPI Intent
        upi_uri = ThermalReceiptGenerator.generate_upi_qr_string(
            vpa=shop.upi_vpa,
            payee_name=shop.business_name,
            amount=invoice.grand_total,
            invoice_number=invoice_number,
        )
        lines.append(center("SCAN & PAY VIA ANY UPI APP"))
        lines.append(center(shop.upi_vpa))
        lines.append("")
        # Include ASCII QR
        qr_ascii = ThermalReceiptGenerator.generate_upi_qr_ascii(upi_uri)
        for qr_line in qr_ascii.strip().split("\n"):
            lines.append(center(qr_line))

        # 6. Footer
        lines.append(divider)
        lines.append(center("Thank You! Visit Again"))
        lines.append(center("நன்றி மீண்டும் வருக"))
        lines.append(divider)

        return "\n".join(lines)

    @staticmethod
    def generate_escpos_bytes(
        text_receipt: str,
    ) -> bytes:
        """Encode receipt text into raw ESC/POS commands with paper cut command."""
        # ESC @ (Initialize printer)
        init_cmd = b"\x1b\x40"
        # Receipt body encoded with utf-8 or cp437 fallback
        body = text_receipt.encode("utf-8", errors="replace")
        # Line feed + Cut Paper (GS V 0)
        cut_cmd = b"\n\n\n\n\x1d\x56\x00"
        return init_cmd + body + cut_cmd
