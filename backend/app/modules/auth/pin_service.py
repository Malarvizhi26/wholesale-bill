"""Server-side owner PIN checks (supervisor overrides, review-flag resolution, PIN change)."""

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    clear_pin_failures,
    is_pin_locked,
    record_pin_failure,
    verify_pin,
)
from app.models.tenant import Tenant

PIN_LOCKED_DETAIL = "Too many wrong owner PIN attempts. Try again in a few minutes."


async def check_owner_pin(session: AsyncSession, tenant_id: str, pin: Optional[str]) -> bool:
    """True if `pin` matches the tenant's owner PIN. Raises 429 while the tenant is locked out."""
    if is_pin_locked(tenant_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=PIN_LOCKED_DETAIL)
    stored_hash = await session.scalar(select(Tenant.owner_pin_hash).where(Tenant.id == tenant_id))
    ok = verify_pin(pin, stored_hash)
    if ok:
        clear_pin_failures(tenant_id)
    else:
        record_pin_failure(tenant_id)
    return ok


async def require_owner_pin(session: AsyncSession, tenant_id: str, pin: Optional[str]) -> None:
    """403 unless a valid owner PIN was supplied (429 while locked out)."""
    if not await check_owner_pin(session, tenant_id, pin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing owner PIN.")
