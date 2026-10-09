"""Multi-tenant context and Row-Level Security session dependency.

Per Section 3.1 of AGENTS.md:
1. Every query must run with tenant isolation enforced at the database level:
   SET LOCAL app.current_tenant_id = '<current_tenant_uuid>';
2. If running on SQLite (local desktop / offline sync / unit tests), the tenant context
   is tracked in a Python context variable and applied as explicit query filters.
"""

from contextvars import ContextVar
from typing import AsyncGenerator, Optional
import uuid
from fastapi import Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory

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


async def get_tenant_db_session(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency that sets the tenant RLS session variable before executing queries."""
    # Fallback to demo default tenant if not specified in development
    effective_tenant_id = x_tenant_id or "00000000-0000-0000-0000-000000000001"
    
    # Validate UUID format
    try:
        uuid.UUID(effective_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tenant UUID format: {effective_tenant_id}",
        )

    # Set Python context variable
    token = current_tenant_id_ctx.set(effective_tenant_id)

    async with async_session_factory() as session:
        try:
            # Set PostgreSQL RLS session variable if on PostgreSQL
            bind = session.bind
            if bind and "postgresql" in str(bind.url):
                await session.execute(
                    text(f"SET LOCAL app.current_tenant_id = '{effective_tenant_id}';")
                )
            
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            current_tenant_id_ctx.reset(token)
            await session.close()
