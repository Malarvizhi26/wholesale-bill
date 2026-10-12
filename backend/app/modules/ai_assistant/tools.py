"""Authoritative fixed tools for AI Business Assistant.

Strict Architecture: The LLM never writes SQL and never performs raw arithmetic.
All business calculations are delegated to these verified domain tools.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timeutils import today_ist
from app.models.catalogue import Product
from app.models.stock import Godown, StockBalance, StockMovement
from app.models.ledger import Party, LedgerEntry
from app.modules.reports.reports_service import ReportsService
from app.modules.ledger.ledger_service import LedgerService
from app.modules.inventory.inventory_service import InventoryService
from app.modules.inventory.unit_converter import SmartUnitConverter

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def _get_date_range_for_period(period: str) -> tuple[date, date]:
    today = today_ist()
    period_upper = (period or "TODAY").upper()
    if period_upper in ("TODAY", "INDRU"):
        return today, today
    elif period_upper in ("YESTERDAY", "NETRU"):
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif period_upper in ("WEEK", "THIS_WEEK", "THIS WEEK", "VARAM"):
        start = today - timedelta(days=today.weekday())  # Start from Monday
        return start, today
    elif period_upper in ("MONTH", "THIS_MONTH", "THIS MONTH", "MAADHAM"):
        start = date(today.year, today.month, 1)
        return start, today
    elif period_upper in ("YEAR", "THIS_YEAR", "THIS YEAR", "AANDU"):
        start_year = today.year if today.month >= 4 else today.year - 1
        start = date(start_year, 4, 1)  # Indian Fiscal Year starts April 1
        return start, today
    elif period_upper in ("ALL", "ALL_TIME"):
        return date(2020, 1, 1), today
    else:
        # Default to month
        start = date(today.year, today.month, 1)
        return start, today


async def get_receivables(
    session: AsyncSession,
    tenant_id: str,
    min_days: int = 0,
    min_amount: Decimal = Decimal("0.00"),
) -> Dict[str, Any]:
    """Fetch customer outstanding receivables, overdue amounts, and aging breakdown."""
    credit_report = await ReportsService.get_outstanding_credit_report(session, tenant_id, limit=None)

    debtors_list = []
    filtered_outstanding = Decimal("0.00")
    filtered_overdue = Decimal("0.00")

    for debtor in credit_report.top_debtors:
        if debtor.current_balance < min_amount:
            continue

        if min_days > 0:
            # Keep only customers holding at least one open bill aged >= min_days (exact per-bill age)
            open_dues = await LedgerService.get_party_open_dues(session, tenant_id, debtor.party_id)
            if not any(inv.age_days >= min_days for inv in open_dues):
                continue

        debtors_list.append({
            "party_id": debtor.party_id,
            "party_name": debtor.party_name,
            "phone": debtor.phone or "-",
            "total_outstanding": debtor.current_balance,
            "total_overdue": debtor.total_overdue,
            "credit_limit": debtor.credit_limit,
            "credit_days": debtor.credit_days,
            "is_credit_exceeded": debtor.is_credit_exceeded,
            "bucket_0_30": debtor.bucket_0_30,
            "bucket_31_60": debtor.bucket_31_60,
            "bucket_61_90": debtor.bucket_61_90,
            "bucket_90_plus": debtor.bucket_90_plus,
        })
        filtered_outstanding += debtor.current_balance
        filtered_overdue += debtor.total_overdue

    return {
        "total_receivables": filtered_outstanding.quantize(TWO_PLACES),
        "total_overdue": filtered_overdue.quantize(TWO_PLACES),
        "debtor_count": len(debtors_list),
        "min_days_filter": min_days,
        "min_amount_filter": min_amount,
        "debtors": debtors_list,
        "action_link": {
            "label_en": "View Outstanding Credit Ledger",
            "label_ta": "கடன் கணக்கு பதிவேடு பார்க்க",
            "route": "/ledger",
            "action_type": "NAVIGATE",
        },
    }


async def profit_by_product(
    session: AsyncSession,
    tenant_id: str,
    period: str = "MONTH",
    top_n: int = 5,
) -> Dict[str, Any]:
    """Calculate profitability by product: sales, cost of goods sold (COGS), gross profit, and margin %."""
    start_date, end_date = _get_date_range_for_period(period)
    margin_report = await ReportsService.get_gross_margin_report(
        session, tenant_id, start_date=start_date, end_date=end_date
    )

    sliced_top = margin_report.top_margin_products[:top_n]
    products_data = []

    for item in sliced_top:
        products_data.append({
            "product_id": item.product_id,
            "product_code": item.product_code,
            "product_name": item.product_name,
            "base_unit": item.base_unit,
            "quantity_sold": item.quantity_sold_base,
            "taxable_sales": item.taxable_sales,
            "cogs": item.cogs,
            "gross_profit": item.gross_profit,
            "margin_percent": item.margin_percent,
        })

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_taxable_sales": margin_report.total_taxable_sales,
        "total_cogs": margin_report.total_cogs,
        "total_gross_profit": margin_report.total_gross_profit,
        "overall_margin_percent": margin_report.overall_margin_percent,
        "top_n": top_n,
        "products": products_data,
        "action_link": {
            "label_en": "View Gross Margin Report",
            "label_ta": "மொத்த லாப அறிக்கை பார்க்க",
            "route": "/reports?tab=margin",
            "action_type": "NAVIGATE",
        },
    }


async def reorder_suggestions(
    session: AsyncSession,
    tenant_id: str,
    godown_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Identify products below minimum stock thresholds and calculate suggested reorder quantities."""
    alerts = await InventoryService.get_low_stock_alerts(session, tenant_id, godown_id=godown_id)

    items = []
    critical_count = 0

    for alert in alerts:
        if alert.alert_severity in ("CRITICAL_NEGATIVE", "OUT_OF_STOCK", "CRITICAL_LOW"):
            critical_count += 1

        items.append({
            "product_id": alert.product_id,
            "product_code": alert.product_code,
            "product_name": alert.product_name,
            "tamil_name": alert.tamil_name or alert.product_name,
            "base_unit": alert.base_unit,
            "current_stock": alert.current_stock_base,
            "display_stock": alert.display_stock,
            "min_stock": alert.min_stock_base,
            "reorder_quantity": alert.reorder_quantity_base,
            "deficit": alert.deficit_base,
            "suggested_reorder": alert.suggested_reorder_base,
            "display_suggested_reorder": alert.display_suggested_reorder,
            "severity": alert.alert_severity,
        })

    return {
        "total_reorder_items": len(items),
        "critical_items_count": critical_count,
        "godown_id": godown_id,
        "items": items,
        "action_link": {
            "label_en": "View Inventory & Alerts",
            "label_ta": "சரக்கு இருப்பு & எச்சரிக்கைகள்",
            "route": "/inventory?tab=alerts",
            "action_type": "NAVIGATE",
        },
    }


async def sales_summary(
    session: AsyncSession,
    tenant_id: str,
    period: str = "TODAY",
    group_by: str = "MODE",
) -> Dict[str, Any]:
    """Summarize sales volume, GST taxes, and payment mode breakdowns."""
    start_date, end_date = _get_date_range_for_period(period)
    sales = await ReportsService.get_daily_sales_summary(
        session, tenant_id, start_date=start_date, end_date=end_date
    )

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_invoices": sales.total_invoices,
        "taxable_amount": sales.taxable_amount,
        "cgst_amount": sales.cgst_amount,
        "sgst_amount": sales.sgst_amount,
        "igst_amount": sales.igst_amount,
        "total_tax": sales.total_tax,
        "round_off": sales.round_off,
        "grand_total": sales.grand_total,
        "sales_by_mode": sales.sales_by_mode,
        "hourly_breakdown": sales.hourly_breakdown,
        "group_by": group_by,
        "action_link": {
            "label_en": "View Daily Sales Report",
            "label_ta": "தினசரி விற்பனை அறிக்கை பார்க்க",
            "route": "/reports?tab=daily",
            "action_type": "NAVIGATE",
        },
    }


async def dead_stock(
    session: AsyncSession,
    tenant_id: str,
    days: int = 60,
) -> Dict[str, Any]:
    """Find stagnant stock holding tied-up capital with no sales or movements in N days."""
    now_utc = datetime.now(timezone.utc)
    cutoff_date = now_utc - timedelta(days=days)

    # Find stock balances with positive quantity
    stmt = (
        select(StockBalance, Product)
        .join(Product, StockBalance.product_id == Product.id)
        .where(
            StockBalance.tenant_id == tenant_id,
            StockBalance.current_quantity_base > 0,
            Product.is_active.is_(True),
        )
        .options(selectinload(Product.units))
    )
    res = await session.execute(stmt)
    rows = res.all()

    dead_items = []
    total_blocked_capital = Decimal("0.00")

    for balance, product in rows:
        # Check last movement date
        last_move_at = balance.last_movement_at
        if not last_move_at:
            # Query most recent movement
            recent_mv_stmt = (
                select(StockMovement.created_at)
                .where(
                    StockMovement.tenant_id == tenant_id,
                    StockMovement.product_id == product.id,
                )
                .order_by(desc(StockMovement.created_at))
                .limit(1)
            )
        if last_move_at:
            if last_move_at.tzinfo is None:
                last_move_at = last_move_at.replace(tzinfo=timezone.utc)
            days_inactive = (now_utc - last_move_at).days
        else:
            days_inactive = 999

        if days_inactive >= days:
            cost = balance.weighted_avg_cost_base if balance.weighted_avg_cost_base > 0 else product.purchase_price_base
            blocked_val = (balance.current_quantity_base * cost).quantize(TWO_PLACES)
            total_blocked_capital += blocked_val

            unit_defs = [
                {"unit_name": u.unit_name, "conversion_factor": u.conversion_factor, "can_buy": u.can_buy, "can_sell": u.can_sell}
                for u in product.units
            ]

            dead_items.append({
                "product_id": product.id,
                "product_code": product.code,
                "product_name": product.name,
                "tamil_name": product.tamil_name or product.name,
                "base_unit": product.base_unit,
                "current_stock": balance.current_quantity_base.quantize(FOUR_PLACES),
                "unit_cost": cost.quantize(TWO_PLACES),
                "tied_up_capital": blocked_val,
                "days_inactive": days_inactive,
                "last_movement_date": last_move_at.strftime("%Y-%m-%d") if last_move_at else "Never",
            })

    dead_items.sort(key=lambda x: x["tied_up_capital"], reverse=True)

    return {
        "days_threshold": days,
        "total_dead_stock_items": len(dead_items),
        "total_tied_up_capital": total_blocked_capital.quantize(TWO_PLACES),
        "items": dead_items,
        "action_link": {
            "label_en": "View Stock Valuation",
            "label_ta": "சரக்கு மதிப்பு அறிக்கை பார்க்க",
            "route": "/reports?tab=valuation",
            "action_type": "NAVIGATE",
        },
    }


async def customer_summary(
    session: AsyncSession,
    tenant_id: str,
    party_name: Optional[str] = None,
    party_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve full credit standing, aging buckets, and unpaid bills for a specific customer."""
    party = None
    if party_id:
        party = await session.scalar(
            select(Party).where(Party.id == party_id, Party.tenant_id == tenant_id)
        )
    elif party_name:
        cleaned_name = party_name.strip()
        stmt = (
            select(Party)
            .where(
                Party.tenant_id == tenant_id,
                or_(
                    Party.name.ilike(f"%{cleaned_name}%"),
                    Party.phone.ilike(f"%{cleaned_name}%"),
                ),
            )
            .limit(1)
        )
        party = await session.scalar(stmt)

    if not party:
        return {
            "found": False,
            "party_name_queried": party_name,
            "message_en": f"No customer found matching '{party_name or party_id}'.",
            "message_ta": f"'{party_name or party_id}' என்ற பெயரில் வாடிக்கையாளர் எவரும் கிடைக்கவில்லை.",
            "action_link": {
                "label_en": "View All Customers in Ledger",
                "label_ta": "அனைத்து வாடிக்கையாளர் கணக்குகளையும் பார்க்க",
                "route": "/ledger",
                "action_type": "NAVIGATE",
            },
        }

    ageing = await LedgerService.get_party_ageing_summary(session, tenant_id, party.id)

    return {
        "found": True,
        "party_id": party.id,
        "party_name": party.name,
        "phone": party.phone or "-",
        "current_balance": ageing.current_balance,
        "credit_limit": ageing.credit_limit,
        "credit_days": ageing.credit_days,
        "is_credit_exceeded": ageing.is_credit_exceeded,
        "total_overdue": ageing.total_overdue,
        "unallocated_advance": ageing.unallocated_advance,
        "bucket_0_30": ageing.bucket_0_30,
        "bucket_31_60": ageing.bucket_31_60,
        "bucket_61_90": ageing.bucket_61_90,
        "bucket_90_plus": ageing.bucket_90_plus,
        "open_invoices_count": len(ageing.open_invoices),
        "open_invoices": [
            {
                "doc_number": inv.doc_number,
                "doc_date": inv.doc_date.isoformat(),
                "due_amount": inv.due_amount,
                "age_days": inv.age_days,
                "is_overdue": inv.is_overdue,
            }
            for inv in ageing.open_invoices[:5]  # Top 5 open invoices
        ],
        "action_link": {
            "label_en": f"Open {party.name}'s Ledger",
            "label_ta": f"{party.name} அவர்களின் கணக்கு பார்க்க",
            "route": f"/ledger?party_id={party.id}",
            "action_type": "NAVIGATE",
        },
    }


async def payables_due(
    session: AsyncSession,
    tenant_id: str,
    days: int = 30,
) -> Dict[str, Any]:
    """Retrieve supplier balances and pending payables."""
    suppliers_report = await LedgerService.get_supplier_balances_summary(session, tenant_id)

    # Filter suppliers where net_payable > 0
    active_suppliers = [s for s in suppliers_report.suppliers if s.net_payable > 0]
    active_suppliers.sort(key=lambda s: s.net_payable, reverse=True)

    supplier_list = []
    for s in active_suppliers:
        supplier_list.append({
            "supplier_id": s.supplier_id,
            "name": s.name,
            "phone": s.phone or "-",
            "net_payable": s.net_payable,
            "total_purchases": s.total_purchases,
            "total_paid": s.total_paid,
            "last_transaction_date": s.last_transaction_date.strftime("%Y-%m-%d") if s.last_transaction_date else "-",
        })

    return {
        "total_net_payable": suppliers_report.total_payable_amount,
        "supplier_count": len(supplier_list),
        "days_filter": days,
        "suppliers": supplier_list,
        "action_link": {
            "label_en": "View Supplier Ledger & Pay",
            "label_ta": "சப்ளையர் கணக்கு & பணம் செலுத்த",
            "route": "/ledger?tab=suppliers",
            "action_type": "NAVIGATE",
        },
    }
