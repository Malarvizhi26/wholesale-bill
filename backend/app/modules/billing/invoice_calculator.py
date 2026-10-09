"""POS Billing & Invoice Calculation Engine.

Strictly enforces:
1. Intra-State (CGST + SGST) vs Inter-State (IGST) split based on State Codes.
2. Exact two-decimal money rounding per line.
3. Accurate round-off to nearest whole rupee within [-0.49, +0.50].
4. Base unit quantity calculation with variable weight support.
"""

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class DiscountType(str, Enum):
    PERCENT = "PERCENT"
    FLAT = "FLAT"


class PaymentMode(str, Enum):
    CASH = "CASH"
    UPI = "UPI"
    CARD = "CARD"
    CREDIT = "CREDIT"
    SPLIT = "SPLIT"


class InvoiceLineInput(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    tamil_name: Optional[str] = None
    unit_name: str
    conversion_factor: Decimal = Field(default=Decimal("1.0"), gt=0)
    quantity: Decimal = Field(gt=0)
    is_variable_weight: bool = False
    actual_weight_kg: Optional[Decimal] = None
    unit_price: Decimal = Field(ge=0)
    cost_price_base: Decimal = Field(default=Decimal("0.0"), ge=0)
    discount_type: DiscountType = DiscountType.FLAT
    discount_value: Decimal = Field(default=Decimal("0.0"), ge=0)
    hsn_code: str
    gst_rate_percent: Decimal = Field(ge=0)


class CalculatedInvoiceLine(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    tamil_name: Optional[str] = None
    unit_name: str
    quantity: Decimal
    base_quantity: Decimal
    unit_price: Decimal
    gross_amount: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    hsn_code: str
    gst_rate_percent: Decimal
    cgst_percent: Decimal
    cgst_amount: Decimal
    sgst_percent: Decimal
    sgst_amount: Decimal
    igst_percent: Decimal
    igst_amount: Decimal
    line_total: Decimal


class CalculatedInvoice(BaseModel):
    lines: List[CalculatedInvoiceLine]
    subtotal_taxable: Decimal
    total_discount: Decimal
    cgst_total: Decimal
    sgst_total: Decimal
    igst_total: Decimal
    tax_total: Decimal
    exact_total: Decimal
    round_off: Decimal
    grand_total: Decimal
    paid_amount: Decimal
    due_amount: Decimal
    is_inter_state: bool


class InvoiceCalculator:
    @staticmethod
    def calculate_invoice(
        lines_input: List[InvoiceLineInput],
        tenant_state_code: str = "33",  # Tamil Nadu default
        place_of_supply_state_code: str = "33",
        paid_amount: Optional[Decimal] = None,
    ) -> CalculatedInvoice:
        is_inter_state = tenant_state_code != place_of_supply_state_code

        calculated_lines: List[CalculatedInvoiceLine] = []
        subtotal_taxable = Decimal("0.00")
        total_discount = Decimal("0.00")
        cgst_total = Decimal("0.00")
        sgst_total = Decimal("0.00")
        igst_total = Decimal("0.00")

        for line in lines_input:
            # 1. Base quantity
            if line.is_variable_weight and line.actual_weight_kg is not None:
                base_qty = line.actual_weight_kg.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            else:
                base_qty = (line.quantity * line.conversion_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

            # 2. Gross Amount
            gross = (line.quantity * line.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # 3. Discount Amount
            if line.discount_type == DiscountType.PERCENT:
                disc = (gross * (line.discount_value / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                disc = line.discount_value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            # Cap discount to gross amount
            disc = min(disc, gross)
            taxable = gross - disc

            # 4. GST Taxes
            if is_inter_state:
                cgst_pct = Decimal("0.00")
                sgst_pct = Decimal("0.00")
                igst_pct = line.gst_rate_percent

                cgst_amt = Decimal("0.00")
                sgst_amt = Decimal("0.00")
                igst_amt = (taxable * (igst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                half_rate = line.gst_rate_percent / Decimal("2")
                cgst_pct = half_rate
                sgst_pct = half_rate
                igst_pct = Decimal("0.00")

                cgst_amt = (taxable * (cgst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                sgst_amt = (taxable * (sgst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                igst_amt = Decimal("0.00")

            line_tot = taxable + cgst_amt + sgst_amt + igst_amt

            calculated_lines.append(
                CalculatedInvoiceLine(
                    product_id=line.product_id,
                    product_code=line.product_code,
                    product_name=line.product_name,
                    tamil_name=line.tamil_name,
                    unit_name=line.unit_name,
                    quantity=line.quantity,
                    base_quantity=base_qty,
                    unit_price=line.unit_price,
                    gross_amount=gross,
                    discount_amount=disc,
                    taxable_amount=taxable,
                    hsn_code=line.hsn_code,
                    gst_rate_percent=line.gst_rate_percent,
                    cgst_percent=cgst_pct,
                    cgst_amount=cgst_amt,
                    sgst_percent=sgst_pct,
                    sgst_amount=sgst_amt,
                    igst_percent=igst_pct,
                    igst_amount=igst_amt,
                    line_total=line_tot,
                )
            )

            subtotal_taxable += taxable
            total_discount += disc
            cgst_total += cgst_amt
            sgst_total += sgst_amt
            igst_total += igst_amt

        tax_total = cgst_total + sgst_total + igst_total
        exact_total = subtotal_taxable + tax_total

        # Grand total rounded to nearest rupee
        grand_total = exact_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(TWO_PLACES)
        round_off = (grand_total - exact_total).quantize(TWO_PLACES)

        paid = paid_amount if paid_amount is not None else grand_total
        due = max(Decimal("0.00"), grand_total - paid).quantize(TWO_PLACES)

        return CalculatedInvoice(
            lines=calculated_lines,
            subtotal_taxable=subtotal_taxable,
            total_discount=total_discount,
            cgst_total=cgst_total,
            sgst_total=sgst_total,
            igst_total=igst_total,
            tax_total=tax_total,
            exact_total=exact_total,
            round_off=round_off,
            grand_total=grand_total,
            paid_amount=paid,
            due_amount=due,
            is_inter_state=is_inter_state,
        )
