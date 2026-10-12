"""Billing POS API router."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.tenant import Tenant
from app.models.stock import StockAlert
from app.modules.auth.pin_service import check_owner_pin, require_owner_pin
from app.models.billing import (
    SalesInvoice,
    SalesReturn,
    Quotation,
    DeliveryChallan,
)
from app.modules.billing.invoice_calculator import (
    CalculatedInvoice,
    InvoiceCalculator,
    InvoiceLineInput,
)
from app.modules.billing.thermal_printer import (
    ShopProfile,
    ThermalReceiptGenerator,
)
from app.modules.billing.billing_service import BillingService
from app.schemas.billing import (
    ProductSearchItemSchema,
    SalesInvoiceCreateSchema,
    SalesInvoiceResponseSchema,
    SalesReturnCreateSchema,
    SalesReturnResponseSchema,
    QuotationCreateSchema,
    QuotationResponseSchema,
    DeliveryChallanCreateSchema,
    DeliveryChallanResponseSchema,
    UnitDecomposeRequestSchema,
    UnitDecomposeResponseSchema,
    ReviewFlagResponseSchema,
    ReviewFlagResolveSchema,
)

router = APIRouter(prefix="/billing", tags=["Billing"])


# -----------------------------------------------------------------------------
# 1. Barcode & Product Search & Unit Conversion
# -----------------------------------------------------------------------------

@router.get("/search", response_model=List[ProductSearchItemSchema])
async def search_products(
    q: str = Query(..., min_length=1, description="Barcode, code, name, or tamil name"),
    godown_id: Optional[str] = Query(None, description="Godown ID for stock balance"),
    price_list_id: Optional[str] = Query(None, description="Price list ID for selling price"),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Instant counter search by barcode, product code, English name, or Tamil name."""
    tenant_id = get_current_tenant_id()
    return await BillingService.search_products_and_barcodes(
        session=session,
        tenant_id=tenant_id,
        query=q,
        godown_id=godown_id,
        price_list_id=price_list_id,
        limit=limit,
    )


@router.post("/unit-decompose", response_model=UnitDecomposeResponseSchema)
async def decompose_unit_quantity(
    payload: UnitDecomposeRequestSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Decompose transaction quantity into base units and packaging display string."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.decompose_unit_quantity(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------------------------------------------------------------------
# 2. Calculation & Receipt Previews
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# 3. GST Sales Invoices
# -----------------------------------------------------------------------------

@router.post("/invoices", response_model=SalesInvoiceResponseSchema, status_code=status.HTTP_201_CREATED)
async def post_sales_invoice(
    payload: SalesInvoiceCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Post completed sales invoice: updates stock movements, stock balances, and party ledger.

    owner_override=true (credit-limit / floor-price breach approval) requires a valid owner_pin:
    403 when the PIN is missing/wrong, 429 while the tenant is locked out after repeated wrong PINs.
    """
    tenant_id = get_current_tenant_id()
    if payload.owner_override:
        await require_owner_pin(session, tenant_id, payload.owner_pin)
    try:
        return await BillingService.create_sales_invoice(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class SyncInvoiceResult(BaseModel):
    invoice_number: Optional[str] = None
    status: str  # 'SYNCED' or 'ERROR'
    invoice_id: Optional[str] = None
    review_flags: List[str] = []
    error: Optional[str] = None


@router.post("/sync-invoices", response_model=List[SyncInvoiceResult])
async def sync_offline_invoices(
    payload: List[SalesInvoiceCreateSchema],
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Push queued offline counter invoices. Conflicts (negative stock, credit limit, floor price)
    are accepted and returned as review_flags; re-sent invoices are idempotent."""
    tenant_id = get_current_tenant_id()
    results: List[SyncInvoiceResult] = []
    for inv_in in payload:
        inv_in.is_offline_created = True
        # Offline bills are never rejected for a bad PIN: the override is simply not recorded as
        # owner-approved, and every conflict is still flagged for owner review.
        if inv_in.owner_override:
            try:
                inv_in.owner_override = await check_owner_pin(session, tenant_id, inv_in.owner_pin)
            except HTTPException:  # locked out
                inv_in.owner_override = False
        try:
            inv = await BillingService.create_sales_invoice(session=session, tenant_id=tenant_id, payload=inv_in)
            results.append(
                SyncInvoiceResult(
                    invoice_number=inv.invoice_number,
                    status="SYNCED",
                    invoice_id=inv.id,
                    review_flags=getattr(inv, "review_flags", []),
                )
            )
        except ValueError as e:
            await session.rollback()
            results.append(SyncInvoiceResult(invoice_number=inv_in.invoice_number, status="ERROR", error=str(e)))
    return results


@router.get("/invoices", response_model=List[SalesInvoiceResponseSchema])
async def list_sales_invoices(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List recent sales invoices."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(SalesInvoice)
        .where(SalesInvoice.tenant_id == tenant_id)
        .options(selectinload(SalesInvoice.lines))
        .order_by(desc(SalesInvoice.invoice_date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/invoices/{invoice_id}", response_model=SalesInvoiceResponseSchema)
async def get_sales_invoice(
    invoice_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Retrieve full sales invoice details."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(SalesInvoice)
        .where(SalesInvoice.id == invoice_id, SalesInvoice.tenant_id == tenant_id)
        .options(selectinload(SalesInvoice.lines))
    )
    inv = await session.scalar(stmt)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


# -----------------------------------------------------------------------------
# 4. Sales Returns / Credit Notes
# -----------------------------------------------------------------------------

@router.post("/returns", response_model=SalesReturnResponseSchema, status_code=status.HTTP_201_CREATED)
async def post_sales_return(
    payload: SalesReturnCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record sales return / credit note: restores stock and updates customer ledger."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.create_sales_return(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/returns", response_model=List[SalesReturnResponseSchema])
async def list_sales_returns(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List recent sales returns / credit notes."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(SalesReturn)
        .where(SalesReturn.tenant_id == tenant_id)
        .options(selectinload(SalesReturn.lines))
        .order_by(desc(SalesReturn.return_date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/returns/{return_id}", response_model=SalesReturnResponseSchema)
async def get_sales_return(
    return_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Retrieve full sales return details."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(SalesReturn)
        .where(SalesReturn.id == return_id, SalesReturn.tenant_id == tenant_id)
        .options(selectinload(SalesReturn.lines))
    )
    ret = await session.scalar(stmt)
    if not ret:
        raise HTTPException(status_code=404, detail="Sales return not found")
    return ret


# -----------------------------------------------------------------------------
# 5. Quotations / Estimates
# -----------------------------------------------------------------------------

class ConvertQuotationRequest(BaseModel):
    payment_mode: str = "CASH"
    paid_amount: Optional[Decimal] = None


@router.post("/quotations", response_model=QuotationResponseSchema, status_code=status.HTTP_201_CREATED)
async def post_quotation(
    payload: QuotationCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Create quotation / price estimate for contractors or retail buyers."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.create_quotation(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/quotations", response_model=List[QuotationResponseSchema])
async def list_quotations(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List quotations."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(Quotation)
        .where(Quotation.tenant_id == tenant_id)
        .options(selectinload(Quotation.lines))
        .order_by(desc(Quotation.quotation_date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/quotations/{quotation_id}", response_model=QuotationResponseSchema)
async def get_quotation(
    quotation_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Get quotation details."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(Quotation)
        .where(Quotation.id == quotation_id, Quotation.tenant_id == tenant_id)
        .options(selectinload(Quotation.lines))
    )
    q = await session.scalar(stmt)
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return q


@router.post("/quotations/{quotation_id}/convert-to-invoice", response_model=SalesInvoiceResponseSchema)
async def convert_quotation(
    quotation_id: str,
    payload: ConvertQuotationRequest = ConvertQuotationRequest(),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """1-Click convert open quotation into a real posted SalesInvoice."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.convert_quotation_to_invoice(
            session=session,
            tenant_id=tenant_id,
            quotation_id=quotation_id,
            payment_mode=payload.payment_mode,
            paid_amount=payload.paid_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -----------------------------------------------------------------------------
# 6. Delivery Challans
# -----------------------------------------------------------------------------

class ConvertChallanRequest(BaseModel):
    payment_mode: str = "CREDIT"
    paid_amount: Optional[Decimal] = None


@router.post("/challans", response_model=DeliveryChallanResponseSchema, status_code=status.HTTP_201_CREATED)
async def post_delivery_challan(
    payload: DeliveryChallanCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Issue Delivery Challan: dispatches goods and decrements stock from godown."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.create_delivery_challan(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/challans", response_model=List[DeliveryChallanResponseSchema])
async def list_delivery_challans(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List delivery challans."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(DeliveryChallan)
        .where(DeliveryChallan.tenant_id == tenant_id)
        .options(selectinload(DeliveryChallan.lines))
        .order_by(desc(DeliveryChallan.challan_date))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/challans/{challan_id}", response_model=DeliveryChallanResponseSchema)
async def get_delivery_challan(
    challan_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Get delivery challan details."""
    tenant_id = get_current_tenant_id()
    stmt = (
        select(DeliveryChallan)
        .where(DeliveryChallan.id == challan_id, DeliveryChallan.tenant_id == tenant_id)
        .options(selectinload(DeliveryChallan.lines))
    )
    dc = await session.scalar(stmt)
    if not dc:
        raise HTTPException(status_code=404, detail="Delivery challan not found")
    return dc


@router.post("/challans/{challan_id}/convert-to-invoice", response_model=SalesInvoiceResponseSchema)
async def convert_challan(
    challan_id: str,
    payload: ConvertChallanRequest = ConvertChallanRequest(),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Convert dispatched delivery challan into final bill without double-deducting stock."""
    tenant_id = get_current_tenant_id()
    try:
        return await BillingService.convert_challan_to_invoice(
            session=session,
            tenant_id=tenant_id,
            challan_id=challan_id,
            payment_mode=payload.payment_mode,
            paid_amount=payload.paid_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



# -----------------------------------------------------------------------------
# 7. Owner Review Flags (negative stock, credit limit, floor price conflicts)
# -----------------------------------------------------------------------------

@router.get("/review-flags", response_model=List[ReviewFlagResponseSchema])
async def list_review_flags(
    status_filter: Literal["OPEN", "RESOLVED", "ALL"] = Query("OPEN", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Owner review queue. Defaults to OPEN items, newest first."""
    tenant_id = get_current_tenant_id()
    stmt = select(StockAlert).where(StockAlert.tenant_id == tenant_id)
    if status_filter != "ALL":
        stmt = stmt.where(StockAlert.status == status_filter)
    stmt = stmt.order_by(desc(StockAlert.created_at)).limit(limit)
    return (await session.execute(stmt)).scalars().all()


@router.post("/review-flags/{flag_id}/resolve", response_model=ReviewFlagResponseSchema)
async def resolve_review_flag(
    flag_id: str,
    payload: ReviewFlagResolveSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Owner marks a review flag as resolved (requires the owner PIN). The flag row is kept."""
    tenant_id = get_current_tenant_id()
    await require_owner_pin(session, tenant_id, payload.owner_pin)
    flag = await session.scalar(
        select(StockAlert).where(StockAlert.id == flag_id, StockAlert.tenant_id == tenant_id)
    )
    if not flag:
        raise HTTPException(status_code=404, detail="Review flag not found")
    if flag.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="Review flag is already resolved")
    flag.status = "RESOLVED"
    flag.resolved_at = datetime.now(timezone.utc)
    flag.resolution_notes = payload.notes
    await session.commit()
    await session.refresh(flag)
    return flag
