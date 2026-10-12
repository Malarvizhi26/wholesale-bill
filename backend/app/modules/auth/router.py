"""Owner PIN API: verify (for UI unlock prompts) and change."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_current_tenant_id, get_tenant_db_session
from app.core.security import hash_pin, is_valid_pin_format
from app.models.tenant import Tenant
from app.modules.auth.pin_service import check_owner_pin, require_owner_pin

router = APIRouter(prefix="/auth", tags=["Auth / Owner PIN"])


class VerifyPinRequest(BaseModel):
    pin: str = Field(..., max_length=32)


class VerifyPinResponse(BaseModel):
    valid: bool


class ChangePinRequest(BaseModel):
    current_pin: str = Field(..., max_length=32)
    new_pin: str = Field(..., max_length=32)


class ChangePinResponse(BaseModel):
    status: str = "ok"


@router.post("/verify-pin", response_model=VerifyPinResponse)
async def verify_owner_pin(
    payload: VerifyPinRequest,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Check the owner PIN. Wrong attempts are throttled per tenant (429 when locked out)."""
    tenant_id = get_current_tenant_id()
    return VerifyPinResponse(valid=await check_owner_pin(session, tenant_id, payload.pin))


@router.post("/change-pin", response_model=ChangePinResponse)
async def change_owner_pin(
    payload: ChangePinRequest,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Change the owner PIN. Requires the current PIN; the new PIN must be 4-8 digits."""
    tenant_id = get_current_tenant_id()
    await require_owner_pin(session, tenant_id, payload.current_pin)
    if not is_valid_pin_format(payload.new_pin):
        raise HTTPException(status_code=422, detail="New PIN must be 4 to 8 digits.")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    tenant.owner_pin_hash = hash_pin(payload.new_pin)
    await session.commit()
    return ChangePinResponse()
