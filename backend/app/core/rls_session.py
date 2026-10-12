"""Multi-tenant context and Row-Level Security session dependency.

Per Section 3.1 of AGENTS.md:
1. Every query must run with tenant isolation enforced at the database level:
   SET LOCAL app.current_tenant_id = '<current_tenant_uuid>';
   On PostgreSQL this is applied at the start of EVERY transaction of the request session
   (services commit mid-request, and SET LOCAL only lives until the transaction ends).
2. If running on SQLite (local desktop / offline sync / unit tests), the tenant context
   is tracked in a Python context variable and applied as explicit query filters.
3. The X-Tenant-ID header is mandatory: a missing or malformed header is a 400, never a
   silent fallback to another tenant.
"""

from contextvars import ContextVar
from typing import AsyncGenerator, Optional
import uuid
from fastapi import Header, HTTPException, status
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.rls_policies import TENANT_SETTING

# Context variable for the active tenant in the current async task
current_tenant_id_ctx: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> str:
    """Retrieve the active tenant ID from context, raising an error if missing."""
    tenant_id = current_tenant_id_ctx.get()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing tenant context. Ensure X-Tenant-ID header is provided.",
        )
    return tenant_id


def normalize_tenant_id(raw: Optional[str]) -> str:
    """Validate the X-Tenant-ID header and return the canonical lower-case UUID text."""
    if not raw or not raw.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Tenant-ID header.",
        )
    try:
        return str(uuid.UUID(raw.strip()))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tenant UUID format: {raw}",
        )


def bind_tenant_to_session(session: AsyncSession, tenant_id: str) -> None:
    """On PostgreSQL, run SET LOCAL app.current_tenant_id at the start of every transaction."""
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return

    def _set_tenant(_sync_session, _transaction, connection) -> None:
        # set_config(..., is_local => true) == SET LOCAL, but with a bound parameter (no SQL injection)
        connection.execute(
            text("SELECT set_config(:setting, :tenant_id, true)"),
            {"setting": TENANT_SETTING, "tenant_id": tenant_id},
        )

    event.listen(session.sync_session, "after_begin", _set_tenant)


async def get_tenant_db_session(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency that sets the tenant RLS session variable before executing queries."""
    effective_tenant_id = normalize_tenant_id(x_tenant_id)

    # Set Python context variable
    token = current_tenant_id_ctx.set(effective_tenant_id)

    async with async_session_factory() as session:
        try:
            bind_tenant_to_session(session, effective_tenant_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            current_tenant_id_ctx.reset(token)
            await session.close()
