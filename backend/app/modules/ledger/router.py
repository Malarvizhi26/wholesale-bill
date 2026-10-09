"""Ledger API router."""

from datetime import date
from decimal import Decimal
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.catalogue import PriceList
from app.models.ledger import Party, LedgerEntry
from app.schemas.ledger import (
    PartyCreateSchema,
    PartyResponseSchema,
    ReceiptVoucherCreateSchema,
    ReceiptVoucherResponseSchema,
    SupplierPaymentCreateSchema,
    SupplierPaymentResponseSchema,
    InvoiceDueItemSchema,
    PartyAgeingSummarySchema,
    SupplierBalancesSummaryResponseSchema,
    CollectionReminderItemSchema,
    DispatchReminderRequestSchema,
    DispatchReminderResponseSchema,
)
from app.modules.ledger.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["Ledger"])


@router.get("/parties", response_model=List[PartyResponseSchema])
async def list_parties(
    party_type: Optional[str] = Query(None, description="CUSTOMER, SUPPLIER, or BOTH"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List customer/supplier parties with balances."""
    tenant_id = get_current_tenant_id()
    query = select(Party).where(Party.tenant_id == tenant_id, Party.is_active.is_(True))

    if party_type:
        query = query.where(Party.party_type == party_type.upper())

    result = await session.execute(query)
    return result.scalars().all()


@router.post("/parties", response_model=PartyResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_party(
    payload: PartyCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Create a new Customer or Supplier party with optional credit limits and opening balance."""
    tenant_id = get_current_tenant_id()
    party_id = str(uuid.uuid4())

    price_list_id = payload.price_list_id
    if not price_list_id and payload.price_list_code:
        pl_stmt = select(PriceList.id).where(
            PriceList.tenant_id == tenant_id,
            PriceList.code == payload.price_list_code.upper()
        )
        pl_res = await session.execute(pl_stmt)
        price_list_id = pl_res.scalar_one_or_none()

    party = Party(
        id=party_id,
        tenant_id=tenant_id,
        party_type=payload.party_type.upper(),
        name=payload.name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        email=payload.email.strip() if payload.email else None,
        gstin=payload.gstin.strip().upper() if payload.gstin else None,
        state_code=payload.state_code,
        billing_address=payload.billing_address,
        price_list_id=price_list_id,
        credit_limit=payload.credit_limit,
        credit_days=payload.credit_days,
        opening_balance=payload.opening_balance,
        current_balance=payload.opening_balance,
        is_active=True,
    )
    session.add(party)

    # If opening balance is specified, register an initial append-only opening balance ledger entry
    if payload.opening_balance != Decimal("0.00"):
        is_debit = payload.opening_balance > Decimal("0.00")
        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            party_id=party_id,
            entry_type="OPENING_BALANCE",
            debit_amount=payload.opening_balance if is_debit else Decimal("0.00"),
            credit_amount=abs(payload.opening_balance) if not is_debit else Decimal("0.00"),
            reference_doc_type="OPENING_BALANCE",
            reference_doc_id=party_id,
            reference_doc_number=f"OB-{party_id[:8].upper()}",
            entry_date=date.today(),
            notes="Opening balance recorded upon party creation",
        )
        session.add(entry)

    await session.commit()
    await session.refresh(party)
    return party


@router.post("/receipts", response_model=ReceiptVoucherResponseSchema, status_code=status.HTTP_201_CREATED)
async def record_customer_receipt(
    payload: ReceiptVoucherCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record customer payment receipt with FIFO auto-allocation or manual invoice matching."""
    tenant_id = get_current_tenant_id()
    try:
        voucher = await LedgerService.record_receipt_voucher(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
        return voucher
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/supplier-payments", response_model=SupplierPaymentResponseSchema, status_code=status.HTTP_201_CREATED)
async def record_supplier_payment(
    payload: SupplierPaymentCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record payment made to supplier: debits supplier ledger and reduces net payable."""
    tenant_id = get_current_tenant_id()
    try:
        voucher = await LedgerService.record_supplier_payment(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
        return voucher
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/parties/{party_id}/dues", response_model=List[InvoiceDueItemSchema])
async def get_party_open_dues(
    party_id: str,
    as_of: Optional[date] = Query(None, description="As of date for ageing calculation"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Fetch invoice-wise open dues with age in days and ageing buckets."""
    tenant_id = get_current_tenant_id()
    try:
        dues = await LedgerService.get_party_open_dues(
            session=session,
            tenant_id=tenant_id,
            party_id=party_id,
            as_of_date=as_of,
        )
        return dues
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/parties/{party_id}/ageing", response_model=PartyAgeingSummarySchema)
async def get_party_ageing(
    party_id: str,
    as_of: Optional[date] = Query(None, description="As of date for ageing calculation"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Fetch 4 ageing buckets (0-30, 31-60, 61-90, 90+), unallocated advance, and credit status."""
    tenant_id = get_current_tenant_id()
    try:
        summary = await LedgerService.get_party_ageing_summary(
            session=session,
            tenant_id=tenant_id,
            party_id=party_id,
            as_of_date=as_of,
        )
        return summary
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/suppliers/summary", response_model=SupplierBalancesSummaryResponseSchema)
async def get_supplier_balances_summary(
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Aggregate total purchases, payments made, and net payables for all suppliers."""
    tenant_id = get_current_tenant_id()
    return await LedgerService.get_supplier_balances_summary(
        session=session,
        tenant_id=tenant_id,
    )


@router.get("/reminders/call-list", response_model=List[CollectionReminderItemSchema])
async def get_collection_call_list(
    min_days_overdue: int = Query(0, ge=0, description="Minimum days overdue"),
    min_amount: Decimal = Query(Decimal("0.00"), ge=0, description="Minimum outstanding balance"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Ranked owner morning call list prioritized by urgency score (Overdue * sqrt(days))."""
    tenant_id = get_current_tenant_id()
    return await LedgerService.get_collection_call_list(
        session=session,
        tenant_id=tenant_id,
        min_days_overdue=min_days_overdue,
        min_amount=min_amount,
    )


@router.post("/reminders/dispatch-whatsapp", response_model=DispatchReminderResponseSchema)
async def dispatch_whatsapp_reminder(
    payload: DispatchReminderRequestSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Dispatch WhatsApp payment reminder with bilingual message & dynamic UPI payment link."""
    tenant_id = get_current_tenant_id()
    try:
        res = await LedgerService.dispatch_whatsapp_reminder(
            session=session,
            tenant_id=tenant_id,
            payload=payload,
        )
        return res
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
