"""Ledger API router."""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.ledger import Party

router = APIRouter(prefix="/ledger", tags=["Ledger"])


class PartyResponseSchema(BaseModel):
    id: str
    party_type: str
    name: str
    phone: Optional[str] = None
    gstin: Optional[str] = None
    state_code: str
    credit_limit: Decimal
    credit_days: int
    current_balance: Decimal
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


@router.get("/parties", response_model=List[PartyResponseSchema])
async def list_parties(
    party_type: Optional[str] = Query(None, description="CUSTOMER, SUPPLIER, or BOTH"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List customer/supplier parties with balances."""
    tenant_id = get_current_tenant_id()
    query = select(Party).where(Party.tenant_id == tenant_id, Party.is_active.is_(True))

    if party_type:
        query = query.where(Party.party_type == party_type)

    result = await session.execute(query)
    return result.scalars().all()
