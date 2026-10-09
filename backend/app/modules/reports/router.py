"""Reports and Analytics API router."""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.modules.reports.reports_service import ReportsService
from app.schemas.reports import (
    DailySalesSummarySchema,
    GrossMarginReportSchema,
    ExpenseCreateSchema,
    ExpenseResponseSchema,
    ExpenseSummarySchema,
    OutstandingCreditReportSchema,
    StockValuationReportSchema,
    CashDrawerReconcileCreateSchema,
    CashDrawerReconcileResponseSchema,
    OwnerMorningSnapshotSchema,
)

router = APIRouter(prefix="/reports", tags=["Reports & Business Analytics"])


@router.get("/sales/daily", response_model=DailySalesSummarySchema)
async def get_daily_sales_summary(
    start_date: Optional[date] = Query(None, description="Start date (defaults to today)"),
    end_date: Optional[date] = Query(None, description="End date (defaults to today)"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Daily sales breakdown: total invoices, taxable value, tax splits, payment modes, and hourly distribution."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_daily_sales_summary(
        session=session,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/margin/gross", response_model=GrossMarginReportSchema)
async def get_gross_margin_report(
    start_date: Optional[date] = Query(None, description="Start date (defaults to today)"),
    end_date: Optional[date] = Query(None, description="End date (defaults to today)"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Gross margin & COGS report calculated against exact Weighted Average Cost (WAC)."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_gross_margin_report(
        session=session,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/expenses", response_model=ExpenseResponseSchema, status_code=status.HTTP_201_CREATED)
async def record_expense(
    payload: ExpenseCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record an operating expense voucher (Rent, Electricity, Tea/Hamali, Wages, Freight, etc.)."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.record_expense(
        session=session,
        tenant_id=tenant_id,
        payload=payload,
    )


@router.get("/expenses", response_model=ExpenseSummarySchema)
async def get_expense_summary(
    start_date: Optional[date] = Query(None, description="Start date (defaults to today)"),
    end_date: Optional[date] = Query(None, description="End date (defaults to today)"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Operating expense summary grouped by category and payment mode."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_expense_summary(
        session=session,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/credit/outstanding", response_model=OutstandingCreditReportSchema)
async def get_outstanding_credit_report(
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Outstanding credit receivables, overdue parties, credit limit breaches, and 4 ageing buckets."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_outstanding_credit_report(
        session=session,
        tenant_id=tenant_id,
    )


@router.get("/stock/valuation", response_model=StockValuationReportSchema)
async def get_stock_valuation_report(
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Inventory valuation across all godowns using Weighted Average Cost (WAC)."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_stock_valuation_report(
        session=session,
        tenant_id=tenant_id,
    )


@router.post("/cash/reconcile", response_model=CashDrawerReconcileResponseSchema, status_code=status.HTTP_201_CREATED)
async def reconcile_cash_drawer(
    payload: CashDrawerReconcileCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Reconcile counter cash drawer: Opening + Cash Sales + Receipts - Expenses - Payouts vs Counted."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.reconcile_cash_drawer(
        session=session,
        tenant_id=tenant_id,
        payload=payload,
    )


@router.get("/owner/snapshot", response_model=OwnerMorningSnapshotSchema)
async def get_owner_morning_snapshot(
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Sub-second morning business snapshot for hardware shop owner."""
    tenant_id = get_current_tenant_id()
    return await ReportsService.get_owner_morning_snapshot(
        session=session,
        tenant_id=tenant_id,
    )
