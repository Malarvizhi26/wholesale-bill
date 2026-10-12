"""Ledger API router."""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal, Optional, Tuple
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.core.timeutils import today_ist
from app.models.catalogue import PriceList
from app.models.ledger import Party, LedgerEntry
from app.schemas.ledger import (
    PartyCreateSchema,
    PartyUpdateSchema,
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

SideParam = Optional[Literal["RECEIVABLE", "PAYABLE"]]


async def _party_responses(session: AsyncSession, tenant_id: str, parties: List[Party]) -> List[PartyResponseSchema]:
    """Party rows with their price list code/name resolved."""
    pl_rows = (
        await session.execute(select(PriceList.id, PriceList.code, PriceList.name).where(PriceList.tenant_id == tenant_id))
    ).all()
    price_lists: Dict[str, Tuple[str, str]] = {pid: (code, name) for pid, code, name in pl_rows}
    out: List[PartyResponseSchema] = []
    for p in parties:
        resp = PartyResponseSchema.model_validate(p, from_attributes=True)
        if p.price_list_id and p.price_list_id in price_lists:
            resp.price_list_code, resp.price_list_name = price_lists[p.price_list_id]
        out.append(resp)
    return out


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
    return await _party_responses(session, tenant_id, list(result.scalars().all()))


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
    # LedgerEntry has no relationship() to Party, so the unit of work cannot order the two INSERTs:
    # flush the party first or PostgreSQL rejects the opening-balance entry's foreign key.
    await session.flush()

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
            entry_date=today_ist(),
            notes="Opening balance recorded upon party creation",
        )
        session.add(entry)

    await session.commit()
    await session.refresh(party)
    return (await _party_responses(session, tenant_id, [party]))[0]


@router.get("/parties/{party_id}", response_model=PartyResponseSchema)
async def get_party(
    party_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Fetch a single customer or supplier party."""
    tenant_id = get_current_tenant_id()
    stmt = select(Party).where(Party.id == party_id, Party.tenant_id == tenant_id)
    res = await session.execute(stmt)
    party = res.scalar_one_or_none()
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Party '{party_id}' not found")
    return (await _party_responses(session, tenant_id, [party]))[0]


@router.put("/parties/{party_id}", response_model=PartyResponseSchema)
@router.patch("/parties/{party_id}", response_model=PartyResponseSchema)
async def update_party(
    party_id: str,
    payload: PartyUpdateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Update customer or supplier details (name, phone, gstin, address, credit limit, price tier, etc.)."""
    tenant_id = get_current_tenant_id()
    stmt = select(Party).where(Party.id == party_id, Party.tenant_id == tenant_id)
    res = await session.execute(stmt)
    party = res.scalar_one_or_none()
    if not party:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Party '{party_id}' not found")

    if payload.name is not None:
        party.name = payload.name.strip()
    if payload.party_type is not None:
        party.party_type = payload.party_type.upper()
    if payload.phone is not None:
        clean_phone = payload.phone.strip()
        party.phone = clean_phone if clean_phone else None
    if payload.email is not None:
        clean_email = payload.email.strip()
        party.email = clean_email if clean_email else None
    if payload.gstin is not None:
        clean_gstin = payload.gstin.strip().upper()
        party.gstin = clean_gstin if clean_gstin else None
    if payload.state_code is not None:
        party.state_code = payload.state_code.strip()
    if payload.billing_address is not None:
        clean_addr = payload.billing_address.strip()
        party.billing_address = clean_addr if clean_addr else None

    # Resolve price list if passed
    if payload.price_list_id is not None:
        party.price_list_id = payload.price_list_id
    elif payload.price_list_code is not None:
        pl_stmt = select(PriceList.id).where(
            PriceList.tenant_id == tenant_id,
            PriceList.code == payload.price_list_code.upper()
        )
        pl_res = await session.execute(pl_stmt)
        party.price_list_id = pl_res.scalar_one_or_none()

    if payload.credit_limit is not None:
        party.credit_limit = payload.credit_limit
    if payload.credit_days is not None:
        party.credit_days = payload.credit_days
    if payload.is_active is not None:
        party.is_active = payload.is_active

    await session.commit()
    await session.refresh(party)
    return (await _party_responses(session, tenant_id, [party]))[0]


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
    as_of: Optional[date] = Query(None, description="As of date for ageing calculation (default: today, IST)"),
    side: SideParam = Query(None, description="RECEIVABLE or PAYABLE (default: PAYABLE for suppliers)"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Fetch bill-wise open dues with age in days and ageing buckets."""
    tenant_id = get_current_tenant_id()
    try:
        dues = await LedgerService.get_party_open_dues(
            session=session,
            tenant_id=tenant_id,
            party_id=party_id,
            as_of_date=as_of,
            side=side,
        )
        return dues
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/parties/{party_id}/ageing", response_model=PartyAgeingSummarySchema)
async def get_party_ageing(
    party_id: str,
    as_of: Optional[date] = Query(None, description="As of date for ageing calculation (default: today, IST)"),
    side: SideParam = Query(None, description="RECEIVABLE or PAYABLE (default: PAYABLE for suppliers)"),
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
            side=side,
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
