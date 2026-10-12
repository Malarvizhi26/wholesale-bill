"""Reports Service: Domain engine for Daily Sales, Gross Margin, Expenses, Credit, Stock Valuation, and Cash Reconciliation."""

from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ist_day_bounds_utc, to_ist, today_ist
from app.models.tenant import NumberSeries
from app.models.catalogue import Product, ProductUnit
from app.models.stock import Godown, StockBalance, StockMovement
from app.models.ledger import Party, LedgerEntry
from app.models.billing import SalesInvoice, SalesInvoiceLine, SalesReturn
from app.models.reports import Expense, CashDrawerSession
from app.modules.ledger.ledger_service import LedgerService
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition
from app.schemas.reports import (
    DailySalesSummarySchema,
    ProductMarginItemSchema,
    GrossMarginReportSchema,
    ExpenseCreateSchema,
    ExpenseResponseSchema,
    ExpenseSummarySchema,
    DebtorSummaryItemSchema,
    OutstandingCreditReportSchema,
    StockValuationItemSchema,
    StockValuationReportSchema,
    CashDrawerReconcileCreateSchema,
    CashDrawerReconcileResponseSchema,
    OwnerMorningSnapshotSchema,
)

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class ReportsService:

    @staticmethod
    def _split_cash_portion(breakdown: Any, paid_amount: Decimal) -> Decimal:
        """Cash part of a SPLIT payment.

        Accepts {"CASH": 500, "UPI": 300} or {"payments": [{"mode": "CASH", "amount": 500}, ...]}
        (or a bare list of such items). Falls back to the full paid amount if no breakdown is stored.
        """
        if not breakdown:
            return paid_amount
        items: List[Any] = []
        if isinstance(breakdown, list):
            items = breakdown
        elif isinstance(breakdown, dict):
            nested = breakdown.get("payments") or breakdown.get("breakdown")
            if isinstance(nested, list):
                items = nested
            else:
                for mode, amt in breakdown.items():
                    if str(mode).upper() == "CASH":
                        return Decimal(str(amt)).quantize(TWO_PLACES)
                return Decimal("0.00")
        cash = Decimal("0.00")
        for it in items:
            if isinstance(it, dict) and str(it.get("mode", "")).upper() == "CASH":
                cash += Decimal(str(it.get("amount", 0)))
        return cash.quantize(TWO_PLACES)

    # -------------------------------------------------------------------------
    # Helper: Number Series
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_next_number(
        session: AsyncSession,
        tenant_id: str,
        doc_type: str,
        default_prefix: str,
        financial_year: str = "2026-27",
    ) -> str:
        stmt = select(NumberSeries).where(
            NumberSeries.tenant_id == tenant_id,
            NumberSeries.doc_type == doc_type,
            NumberSeries.financial_year == financial_year,
        )
        res = await session.execute(stmt)
        series = res.scalar_one_or_none()

        if not series:
            # Check highest existing number in Expense to avoid collision with pre-seeded data
            existing_vouchers = (await session.execute(
                select(Expense.voucher_number).where(Expense.tenant_id == tenant_id)
            )).scalars().all()
            max_num = 0
            for v in existing_vouchers:
                if v and v.startswith(default_prefix):
                    try:
                        max_num = max(max_num, int(v[len(default_prefix):]))
                    except ValueError:
                        pass
            num = max_num + 1
            series = NumberSeries(
                tenant_id=tenant_id,
                doc_type=doc_type,
                financial_year=financial_year,
                prefix=default_prefix,
                current_number=num,
                range_start=1,
                range_end=999999,
            )
            session.add(series)
        else:
            series.current_number += 1
            while True:
                num = series.current_number
                candidate = f"{series.prefix}{num:04d}"
                exists = (await session.execute(
                    select(Expense.id).where(Expense.tenant_id == tenant_id, Expense.voucher_number == candidate)
                )).scalar_one_or_none()
                if not exists:
                    break
                series.current_number += 1

        return f"{series.prefix}{num:04d}"

    # -------------------------------------------------------------------------
    # 1. Daily Sales Summary
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_daily_sales_summary(
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> DailySalesSummarySchema:
        """Aggregate total sales, tax split, payment modes, and hourly distribution (IST days and hours)."""
        if not start_date:
            start_date = today_ist()
        if not end_date:
            end_date = start_date

        start_dt, end_dt = ist_day_bounds_utc(start_date, end_date)

        stmt = select(SalesInvoice).where(
            SalesInvoice.tenant_id == tenant_id,
            SalesInvoice.status == "POSTED",
            SalesInvoice.invoice_date >= start_dt,
            SalesInvoice.invoice_date < end_dt,
        )
        res = await session.execute(stmt)
        invoices = res.scalars().all()

        total_invoices = len(invoices)
        taxable_amount = Decimal("0.00")
        cgst_amount = Decimal("0.00")
        sgst_amount = Decimal("0.00")
        igst_amount = Decimal("0.00")
        total_tax = Decimal("0.00")
        round_off = Decimal("0.00")
        grand_total = Decimal("0.00")
        sales_by_mode: Dict[str, Decimal] = {
            "CASH": Decimal("0.00"),
            "UPI": Decimal("0.00"),
            "CREDIT": Decimal("0.00"),
            "CARD": Decimal("0.00"),
            "SPLIT": Decimal("0.00"),
        }
        hours_map: Dict[int, Dict[str, Any]] = {h: {"hour": h, "count": 0, "amount": Decimal("0.00")} for h in range(24)}

        for inv in invoices:
            # subtotal_amount is already the post-discount taxable value (sum of line taxable amounts)
            taxable_amount += inv.subtotal_amount
            cgst_amount += inv.cgst_amount
            sgst_amount += inv.sgst_amount
            igst_amount += inv.igst_amount
            total_tax += inv.total_tax_amount
            round_off += inv.round_off_amount
            grand_total += inv.grand_total

            mode = inv.payment_mode.upper() if inv.payment_mode else "CASH"
            sales_by_mode[mode] = sales_by_mode.get(mode, Decimal("0.00")) + inv.grand_total

            hr = to_ist(inv.invoice_date).hour if inv.invoice_date else 0
            hours_map[hr]["count"] += 1
            hours_map[hr]["amount"] += inv.grand_total

        hourly_list = [
            {"hour": f"{h:02d}:00", "invoice_count": data["count"], "total_sales": data["amount"].quantize(TWO_PLACES)}
            for h, data in sorted(hours_map.items())
            if data["count"] > 0
        ]

        return DailySalesSummarySchema(
            period_start=start_date,
            period_end=end_date,
            total_invoices=total_invoices,
            taxable_amount=taxable_amount.quantize(TWO_PLACES),
            cgst_amount=cgst_amount.quantize(TWO_PLACES),
            sgst_amount=sgst_amount.quantize(TWO_PLACES),
            igst_amount=igst_amount.quantize(TWO_PLACES),
            total_tax=total_tax.quantize(TWO_PLACES),
            round_off=round_off.quantize(TWO_PLACES),
            grand_total=grand_total.quantize(TWO_PLACES),
            sales_by_mode={k: v.quantize(TWO_PLACES) for k, v in sales_by_mode.items() if v > 0},
            hourly_breakdown=hourly_list,
        )

    # -------------------------------------------------------------------------
    # 2. Gross Margin & Profitability
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_gross_margin_report(
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> GrossMarginReportSchema:
        """Calculate sales revenue, COGS based on WAC, and gross margin per product & overall."""
        if not start_date:
            start_date = today_ist()
        if not end_date:
            end_date = start_date

        start_dt, end_dt = ist_day_bounds_utc(start_date, end_date)

        stmt = (
            select(SalesInvoiceLine, SalesInvoice, Product)
            .join(SalesInvoice, SalesInvoiceLine.invoice_id == SalesInvoice.id)
            .join(Product, SalesInvoiceLine.product_id == Product.id)
            .where(
                SalesInvoice.tenant_id == tenant_id,
                SalesInvoice.status == "POSTED",
                SalesInvoice.invoice_date >= start_dt,
                SalesInvoice.invoice_date < end_dt,
            )
        )
        res = await session.execute(stmt)
        rows = res.all()

        prod_aggregates: Dict[str, Dict[str, Any]] = {}
        total_taxable = Decimal("0.00")
        total_cogs = Decimal("0.00")

        for line, inv, prod in rows:
            line_cogs = (line.base_quantity * line.cost_price_base_at_sale).quantize(TWO_PLACES)
            if line_cogs == Decimal("0.00") and prod.purchase_price_base > 0:
                line_cogs = (line.base_quantity * prod.purchase_price_base).quantize(TWO_PLACES)

            line_profit = (line.taxable_amount - line_cogs).quantize(TWO_PLACES)

            total_taxable += line.taxable_amount
            total_cogs += line_cogs

            pid = prod.id
            if pid not in prod_aggregates:
                prod_aggregates[pid] = {
                    "product_id": pid,
                    "product_code": prod.code,
                    "product_name": prod.name,
                    "base_unit": prod.base_unit,
                    "quantity_sold_base": Decimal("0.0000"),
                    "taxable_sales": Decimal("0.00"),
                    "cogs": Decimal("0.00"),
                    "gross_profit": Decimal("0.00"),
                }

            prod_aggregates[pid]["quantity_sold_base"] += line.base_quantity
            prod_aggregates[pid]["taxable_sales"] += line.taxable_amount
            prod_aggregates[pid]["cogs"] += line_cogs
            prod_aggregates[pid]["gross_profit"] += line_profit

        items: List[ProductMarginItemSchema] = []
        for pdata in prod_aggregates.values():
            tax_sales = pdata["taxable_sales"]
            profit = pdata["gross_profit"]
            margin_pct = (profit / tax_sales * Decimal("100.00")).quantize(TWO_PLACES) if tax_sales > 0 else Decimal("0.00")

            items.append(
                ProductMarginItemSchema(
                    product_id=pdata["product_id"],
                    product_code=pdata["product_code"],
                    product_name=pdata["product_name"],
                    base_unit=pdata["base_unit"],
                    quantity_sold_base=pdata["quantity_sold_base"].quantize(FOUR_PLACES),
                    taxable_sales=pdata["taxable_sales"].quantize(TWO_PLACES),
                    cogs=pdata["cogs"].quantize(TWO_PLACES),
                    gross_profit=profit.quantize(TWO_PLACES),
                    margin_percent=margin_pct,
                )
            )

        items.sort(key=lambda x: x.gross_profit, reverse=True)
        top_products = items[:10]
        low_products = sorted(items, key=lambda x: x.margin_percent)[:10]

        total_profit = (total_taxable - total_cogs).quantize(TWO_PLACES)
        overall_pct = (total_profit / total_taxable * Decimal("100.00")).quantize(TWO_PLACES) if total_taxable > 0 else Decimal("0.00")

        return GrossMarginReportSchema(
            period_start=start_date,
            period_end=end_date,
            total_taxable_sales=total_taxable.quantize(TWO_PLACES),
            total_cogs=total_cogs.quantize(TWO_PLACES),
            total_gross_profit=total_profit.quantize(TWO_PLACES),
            overall_margin_percent=overall_pct,
            top_margin_products=top_products,
            low_margin_products=low_products,
        )

    # -------------------------------------------------------------------------
    # 3. Expenses
    # -------------------------------------------------------------------------
    @staticmethod
    async def record_expense(
        session: AsyncSession,
        tenant_id: str,
        payload: ExpenseCreateSchema,
    ) -> ExpenseResponseSchema:
        """Create and record an operating expense voucher."""
        voucher_number = await ReportsService.get_next_number(
            session=session,
            tenant_id=tenant_id,
            doc_type="EXPENSE_VOUCHER",
            default_prefix="EXP/26-27/",
        )

        expense_id = str(uuid.uuid4())
        expense_date = payload.expense_date or today_ist()

        expense = Expense(
            id=expense_id,
            tenant_id=tenant_id,
            voucher_number=voucher_number,
            expense_date=expense_date,
            category=payload.category.upper(),
            amount=payload.amount,
            payment_mode=payload.payment_mode.upper(),
            vendor_or_recipient=payload.vendor_or_recipient.strip(),
            reference_number=payload.reference_number,
            is_direct_expense=payload.is_direct_expense,
            notes=payload.notes,
        )
        session.add(expense)
        await session.commit()
        await session.refresh(expense)

        return ExpenseResponseSchema.model_validate(expense)

    @staticmethod
    async def get_expense_summary(
        session: AsyncSession,
        tenant_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> ExpenseSummarySchema:
        """Aggregate expenses in date range grouped by category and payment mode."""
        if not start_date:
            start_date = today_ist()
        if not end_date:
            end_date = start_date

        stmt = (
            select(Expense)
            .where(
                Expense.tenant_id == tenant_id,
                Expense.expense_date >= start_date,
                Expense.expense_date <= end_date,
            )
            .order_by(Expense.expense_date.desc(), Expense.created_at.desc())
        )
        res = await session.execute(stmt)
        expenses = res.scalars().all()

        total_expenses = Decimal("0.00")
        cash_expenses = Decimal("0.00")
        bank_upi_expenses = Decimal("0.00")
        by_category: Dict[str, Decimal] = {}

        for exp in expenses:
            total_expenses += exp.amount
            if exp.payment_mode.upper() == "CASH":
                cash_expenses += exp.amount
            else:
                bank_upi_expenses += exp.amount

            cat = exp.category.upper()
            by_category[cat] = by_category.get(cat, Decimal("0.00")) + exp.amount

        return ExpenseSummarySchema(
            period_start=start_date,
            period_end=end_date,
            total_expenses=total_expenses.quantize(TWO_PLACES),
            cash_expenses=cash_expenses.quantize(TWO_PLACES),
            bank_upi_expenses=bank_upi_expenses.quantize(TWO_PLACES),
            by_category={k: v.quantize(TWO_PLACES) for k, v in by_category.items()},
            expenses=[ExpenseResponseSchema.model_validate(e) for e in expenses],
        )

    # -------------------------------------------------------------------------
    # 4. Outstanding Credit & Receivables
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_outstanding_credit_report(
        session: AsyncSession,
        tenant_id: str,
        limit: Optional[int] = 50,
    ) -> OutstandingCreditReportSchema:
        """Aggregate total receivables, overdue count, and 4 ageing buckets."""
        stmt = (
            select(Party)
            .where(
                Party.tenant_id == tenant_id,
                Party.is_active.is_(True),
                Party.current_balance > 0,
                or_(Party.party_type == "CUSTOMER", Party.party_type == "BOTH"),
            )
            .order_by(Party.current_balance.desc())
        )
        res = await session.execute(stmt)
        parties = res.scalars().all()

        total_receivables = Decimal("0.00")
        total_overdue = Decimal("0.00")
        breached_count = 0
        b_0_30 = Decimal("0.00")
        b_31_60 = Decimal("0.00")
        b_61_90 = Decimal("0.00")
        b_90_plus = Decimal("0.00")

        debtor_items: List[DebtorSummaryItemSchema] = []

        for p in parties:
            total_receivables += p.current_balance
            ageing = await LedgerService.get_party_ageing_summary(session, tenant_id, p.id)

            b_0_30 += ageing.bucket_0_30
            b_31_60 += ageing.bucket_31_60
            b_61_90 += ageing.bucket_61_90
            b_90_plus += ageing.bucket_90_plus
            total_overdue += ageing.total_overdue

            if ageing.is_credit_exceeded:
                breached_count += 1

            oldest_overdue = 0
            if ageing.open_invoices:
                oldest_overdue = max(0, ageing.open_invoices[0].age_days - p.credit_days)

            debtor_items.append(
                DebtorSummaryItemSchema(
                    party_id=p.id,
                    party_name=p.name,
                    phone=p.phone,
                    credit_limit=p.credit_limit,
                    credit_days=p.credit_days,
                    current_balance=p.current_balance,
                    is_credit_exceeded=ageing.is_credit_exceeded,
                    days_overdue=oldest_overdue,
                    bucket_0_30=ageing.bucket_0_30,
                    bucket_31_60=ageing.bucket_31_60,
                    bucket_61_90=ageing.bucket_61_90,
                    bucket_90_plus=ageing.bucket_90_plus,
                    total_overdue=ageing.total_overdue,
                )
            )

        return OutstandingCreditReportSchema(
            total_parties=len(debtor_items),
            total_receivables=total_receivables.quantize(TWO_PLACES),
            total_overdue=total_overdue.quantize(TWO_PLACES),
            breached_parties_count=breached_count,
            bucket_0_30=b_0_30.quantize(TWO_PLACES),
            bucket_31_60=b_31_60.quantize(TWO_PLACES),
            bucket_61_90=b_61_90.quantize(TWO_PLACES),
            bucket_90_plus=b_90_plus.quantize(TWO_PLACES),
            top_debtors=debtor_items[:limit] if limit else debtor_items,
        )

    # -------------------------------------------------------------------------
    # 5. Stock Valuation
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_stock_valuation_report(
        session: AsyncSession,
        tenant_id: str,
    ) -> StockValuationReportSchema:
        """Calculate total inventory valuation based on exact WAC across godowns."""
        prod_stmt = select(Product).where(Product.tenant_id == tenant_id, Product.is_active.is_(True)).order_by(Product.name.asc())
        products = (await session.execute(prod_stmt)).scalars().all()

        total_cost_val = Decimal("0.00")
        total_retail_val = Decimal("0.00")
        low_stock_count = 0
        godown_vals: Dict[str, Decimal] = {}
        items: List[StockValuationItemSchema] = []

        for p in products:
            # Query stock balance across godowns
            sb_stmt = select(StockBalance).where(StockBalance.tenant_id == tenant_id, StockBalance.product_id == p.id)
            balances = (await session.execute(sb_stmt)).scalars().all()

            qty_base = sum((b.current_quantity_base for b in balances), Decimal("0.0000"))

            # Each godown carries its own WAC: value = sum(godown qty x godown WAC); negative stock is valued at 0
            per_godown_vals: Dict[str, Decimal] = {}
            for b in balances:
                b_wac = b.weighted_avg_cost_base if b.weighted_avg_cost_base > 0 else p.purchase_price_base
                per_godown_vals[b.godown_id] = (max(Decimal("0.0000"), b.current_quantity_base) * b_wac).quantize(TWO_PLACES)
            val_cost = sum(per_godown_vals.values(), Decimal("0.00")).quantize(TWO_PLACES)

            positive_qty = sum((max(Decimal("0.0000"), b.current_quantity_base) for b in balances), Decimal("0.0000"))
            if positive_qty > 0:
                wac_base = (val_cost / positive_qty).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            else:
                wac_base = next((b.weighted_avg_cost_base for b in balances if b.weighted_avg_cost_base > 0), p.purchase_price_base)
            # Estimate retail value at ~15-20% margin
            val_retail = (val_cost * Decimal("1.18")).quantize(TWO_PLACES)

            total_cost_val += val_cost
            total_retail_val += val_retail

            is_low = bool(qty_base <= p.min_stock_base)
            if is_low:
                low_stock_count += 1

            # Format display stock
            conv_units = [
                UnitDefinition(
                    unit_name=u.unit_name,
                    conversion_factor=u.conversion_factor,
                    can_buy=u.can_buy,
                    can_sell=u.can_sell,
                )
                for u in p.units
            ]
            disp = SmartUnitConverter.to_display_units(qty_base, p.base_unit, conv_units)

            # Godown allocation
            for gid, gval in per_godown_vals.items():
                godown_vals[gid] = godown_vals.get(gid, Decimal("0.00")) + gval

            items.append(
                StockValuationItemSchema(
                    product_id=p.id,
                    product_code=p.code,
                    product_name=p.name,
                    base_unit=p.base_unit,
                    current_stock_base=qty_base.quantize(FOUR_PLACES),
                    wac_base=wac_base.quantize(FOUR_PLACES),
                    valuation_cost=val_cost,
                    display_stock=disp,
                    is_low_stock=is_low,
                )
            )

        items.sort(key=lambda x: x.valuation_cost, reverse=True)

        return StockValuationReportSchema(
            total_products=len(items),
            total_valuation_cost=total_cost_val.quantize(TWO_PLACES),
            total_retail_value=total_retail_val.quantize(TWO_PLACES),
            low_stock_count=low_stock_count,
            godown_valuations={k: v.quantize(TWO_PLACES) for k, v in godown_vals.items()},
            items=items,
        )

    # -------------------------------------------------------------------------
    # 6. Cash Reconciliation & Counter Drawer
    # -------------------------------------------------------------------------
    @staticmethod
    async def reconcile_cash_drawer(
        session: AsyncSession,
        tenant_id: str,
        payload: CashDrawerReconcileCreateSchema,
    ) -> CashDrawerReconcileResponseSchema:
        """Calculate expected drawer cash vs counted cash and save reconciliation voucher."""
        session_date = payload.session_date or today_ist()
        start_dt, end_dt = ist_day_bounds_utc(session_date)

        # 1. Cash Sales from SalesInvoices (only the CASH portion of SPLIT bills)
        cash_inv_stmt = select(SalesInvoice).where(
            SalesInvoice.tenant_id == tenant_id,
            SalesInvoice.status == "POSTED",
            SalesInvoice.invoice_date >= start_dt,
            SalesInvoice.invoice_date < end_dt,
            or_(SalesInvoice.payment_mode == "CASH", SalesInvoice.payment_mode == "SPLIT"),
        )
        cash_sales = Decimal("0.00")
        for inv in (await session.execute(cash_inv_stmt)).scalars().all():
            if inv.payment_mode == "SPLIT":
                cash_sales += ReportsService._split_cash_portion(inv.payment_breakdown, inv.paid_amount)
            else:
                cash_sales += inv.paid_amount

        # 2. Cash Receipts from Receipt Vouchers. Counter payments posted with an invoice
        #    (reference_doc_type SALES_INVOICE) are already part of cash sales above.
        cash_rc_stmt = select(func.coalesce(func.sum(LedgerEntry.credit_amount), Decimal("0"))).where(
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.entry_date == session_date,
            LedgerEntry.entry_type == "PAYMENT_RECEIPT",
            LedgerEntry.reference_doc_type == "RECEIPT_VOUCHER",
            LedgerEntry.credit_amount > 0,
            LedgerEntry.notes.like("%via CASH%"),
        )
        cash_receipts = await session.scalar(cash_rc_stmt) or Decimal("0.00")

        # 2b. Cash refunds paid out of the drawer on sales returns
        cash_refunds = await ReportsService._cash_refunds_between(session, tenant_id, start_dt, end_dt)

        # 3. Cash Expenses Paid
        cash_exp_stmt = select(func.coalesce(func.sum(Expense.amount), Decimal("0"))).where(
            Expense.tenant_id == tenant_id,
            Expense.expense_date == session_date,
            Expense.payment_mode == "CASH",
        )
        cash_expenses = await session.scalar(cash_exp_stmt) or Decimal("0.00")

        # 4. Cash Supplier Payments
        cash_sup_stmt = select(func.coalesce(func.sum(LedgerEntry.debit_amount), Decimal("0"))).where(
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.entry_date == session_date,
            LedgerEntry.entry_type == "SUPPLIER_PAYMENT",
            LedgerEntry.notes.like("%via CASH%"),
        )
        cash_sup_payouts = await session.scalar(cash_sup_stmt) or Decimal("0.00")

        # Expected Cash in Drawer
        expected_cash = (
            payload.opening_cash + cash_sales + cash_receipts - cash_refunds - cash_expenses - cash_sup_payouts
        ).quantize(TWO_PLACES)
        discrepancy = (payload.actual_cash_counted - expected_cash).quantize(TWO_PLACES)

        session_code = await ReportsService.get_next_number(
            session=session,
            tenant_id=tenant_id,
            doc_type="CASH_RECONCILIATION",
            default_prefix="CR/26-27/",
        )

        now = datetime.now(timezone.utc)
        drawer_session = CashDrawerSession(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            session_code=session_code,
            counter_name=payload.counter_name,
            cashier_name=payload.cashier_name,
            session_date=session_date,
            opened_at=start_dt,
            closed_at=now,
            status="RECONCILED",
            opening_cash=payload.opening_cash,
            cash_sales_amount=cash_sales,
            cash_ledger_receipts=cash_receipts,
            cash_refunds_paid=cash_refunds,
            cash_expenses_paid=cash_expenses,
            cash_supplier_payouts=cash_sup_payouts,
            expected_cash_drawer=expected_cash,
            actual_cash_counted=payload.actual_cash_counted,
            discrepancy_amount=discrepancy,
            denominations=payload.denominations,
            notes=payload.notes,
        )
        session.add(drawer_session)
        await session.commit()
        await session.refresh(drawer_session)

        return CashDrawerReconcileResponseSchema.model_validate(drawer_session)

    @staticmethod
    async def _cash_refunds_between(session: AsyncSession, tenant_id: str, start_dt: datetime, end_dt: datetime) -> Decimal:
        """Sum of CASH refunds on sales returns in [start_dt, end_dt)."""
        total = await session.scalar(
            select(func.coalesce(func.sum(SalesReturn.grand_total), Decimal("0"))).where(
                SalesReturn.tenant_id == tenant_id,
                SalesReturn.refund_mode == "CASH",
                SalesReturn.return_date >= start_dt,
                SalesReturn.return_date < end_dt,
            )
        )
        return Decimal(total or 0).quantize(TWO_PLACES)

    # -------------------------------------------------------------------------
    # 7. Owner Morning Snapshot (< 1 second load)
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_owner_morning_snapshot(
        session: AsyncSession,
        tenant_id: str,
    ) -> OwnerMorningSnapshotSchema:
        """Fast aggregated owner morning snapshot satisfying Module 4 of AGENTS.md."""
        today = today_ist()
        start_dt, end_dt = ist_day_bounds_utc(today)

        # 1. Sales today
        sales_summary = await ReportsService.get_daily_sales_summary(session, tenant_id, today, today)

        # 2. Margin estimate today
        margin_report = await ReportsService.get_gross_margin_report(session, tenant_id, today, today)

        # 3. Expenses today
        expenses_summary = await ReportsService.get_expense_summary(session, tenant_id, today, today)
        net_profit = margin_report.total_gross_profit - expenses_summary.total_expenses

        # 4. Receivables & Debtors
        credit_report = await ReportsService.get_outstanding_credit_report(session, tenant_id, limit=None)

        # 5. Payables due to suppliers
        sup_stmt = select(func.coalesce(func.sum(Party.current_balance), Decimal("0"))).where(
            Party.tenant_id == tenant_id,
            Party.is_active.is_(True),
            Party.current_balance < 0,
            or_(Party.party_type == "SUPPLIER", Party.party_type == "BOTH"),
        )
        sup_balance_sum = await session.scalar(sup_stmt) or Decimal("0.00")
        payables_due = abs(sup_balance_sum).quantize(TWO_PLACES)

        # 6. Stock valuation & alerts
        stock_report = await ReportsService.get_stock_valuation_report(session, tenant_id)

        # 7. Cash in drawer estimate (Cash sales + opening cash - cash expenses)
        cash_refunds_today = await ReportsService._cash_refunds_between(session, tenant_id, start_dt, end_dt)
        cash_in_drawer = (
            sales_summary.sales_by_mode.get("CASH", Decimal("0.00")) - cash_refunds_today - expenses_summary.cash_expenses
        )
        if cash_in_drawer < 0:
            cash_in_drawer = Decimal("0.00")

        top_prod = margin_report.top_margin_products[0].product_name if margin_report.top_margin_products else None

        return OwnerMorningSnapshotSchema(
            today_sales=sales_summary.grand_total,
            invoices_count_today=sales_summary.total_invoices,
            gross_margin_estimate=margin_report.total_gross_profit,
            gross_margin_percent=margin_report.overall_margin_percent,
            operating_expenses_today=expenses_summary.total_expenses,
            net_operating_profit_today=net_profit.quantize(TWO_PLACES),
            cash_in_drawer=cash_in_drawer.quantize(TWO_PLACES),
            outstanding_receivables=credit_report.total_receivables,
            overdue_debtors_count=len([d for d in credit_report.top_debtors if d.days_overdue > 0]),
            payables_due_suppliers=payables_due,
            stock_total_valuation=stock_report.total_valuation_cost,
            low_stock_alerts_count=stock_report.low_stock_count,
            top_selling_product=top_prod,
        )
