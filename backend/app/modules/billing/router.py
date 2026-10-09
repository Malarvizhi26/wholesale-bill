"""Billing POS API router."""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.tenant import Tenant
from app.modules.billing.invoice_calculator import (
    CalculatedInvoice,
    InvoiceCalculator,
    InvoiceLineInput,
)
from app.modules.billing.thermal_printer import (
    ShopProfile,
    ThermalReceiptGenerator,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


class CalculateInvoiceRequest(BaseModel):
    place_of_supply_state_code: str = "33"
    lines: List[InvoiceLineInput]
    paid_amount: Optional[Decimal] = None


class ReceiptPreviewRequest(BaseModel):
    invoice_number: str
    invoice_date_str: str = "09-Oct-2026 12:00"
    counter_code: str = "COUNTER-1"
    customer_name: str = "Walk-in Retail"
    customer_phone: Optional[str] = None
    place_of_supply_state_code: str = "33"
    lines: List[InvoiceLineInput]
    paid_amount: Optional[Decimal] = None


@router.post("/calculate", response_model=CalculatedInvoice)
async def calculate_bill(
    payload: CalculateInvoiceRequest,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Run GST and line calculation for a POS draft bill."""
    tenant_id = get_current_tenant_id()
    tenant_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()
    tenant_state = tenant.state_code if tenant else "33"

    calculated = InvoiceCalculator.calculate_invoice(
        lines_input=payload.lines,
        tenant_state_code=tenant_state,
        place_of_supply_state_code=payload.place_of_supply_state_code,
        paid_amount=payload.paid_amount,
    )
    return calculated


@router.post("/receipt-preview")
async def preview_thermal_receipt(
    payload: ReceiptPreviewRequest,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Generate exact thermal receipt text and dynamic UPI QR code."""
    tenant_id = get_current_tenant_id()
    tenant_res = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = tenant_res.scalar_one_or_none()

    shop = ShopProfile(
        business_name=tenant.business_name if tenant else "Hardware Store",
        trade_name=tenant.trade_name if tenant else None,
        gstin=tenant.gstin if tenant else None,
        phone=tenant.phone if tenant else "9876543210",
        address=f"{tenant.address_line1}, {tenant.city}" if tenant else "Salem",
        upi_vpa="store@icici",
    )

    tenant_state = tenant.state_code if tenant else "33"
    invoice = InvoiceCalculator.calculate_invoice(
        lines_input=payload.lines,
        tenant_state_code=tenant_state,
        place_of_supply_state_code=payload.place_of_supply_state_code,
        paid_amount=payload.paid_amount,
    )

    receipt_text = ThermalReceiptGenerator.format_text_receipt(
        shop=shop,
        invoice=invoice,
        invoice_number=payload.invoice_number,
        invoice_date_str=payload.invoice_date_str,
        counter_code=payload.counter_code,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
    )

    upi_intent = ThermalReceiptGenerator.generate_upi_qr_string(
        vpa=shop.upi_vpa,
        payee_name=shop.business_name,
        amount=invoice.grand_total,
        invoice_number=payload.invoice_number,
    )

    return {
        "invoice_number": payload.invoice_number,
        "grand_total": invoice.grand_total,
        "upi_intent": upi_intent,
        "receipt_text": receipt_text,
    }
