"""Ledger Service: Domain engine for Party Ledger, FIFO Allocation, Ageing, Suppliers, and Reminders."""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Dict, List, Optional, Tuple
import uuid

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import today_ist
from app.models.tenant import Tenant, NumberSeries
from app.models.ledger import Party, LedgerEntry, PaymentAllocation, CollectionReminderLog
from app.modules.billing.thermal_printer import ThermalReceiptGenerator
from app.schemas.ledger import (
    ReceiptVoucherCreateSchema,
    ReceiptVoucherResponseSchema,
    AllocationDetailSchema,
    SupplierPaymentCreateSchema,
    SupplierPaymentResponseSchema,
    InvoiceDueItemSchema,
    PartyAgeingSummarySchema,
    SupplierBalanceItemSchema,
    SupplierBalancesSummaryResponseSchema,
    CollectionReminderItemSchema,
    DispatchReminderRequestSchema,
    DispatchReminderResponseSchema,
)

TWO_PLACES = Decimal("0.01")

# Supplier-side documents never count as customer receivables (matters for party_type 'BOTH')
SUPPLIER_ENTRY_TYPES = ("SUPPLIER_PAYMENT", "PURCHASE_BILL")


def default_side(party: Party) -> str:
    """Receivable (customer bills) unless the party is a pure supplier."""
    return "PAYABLE" if party.party_type == "SUPPLIER" else "RECEIVABLE"


def _bucket(age_days: int) -> str:
    if age_days <= 30:
        return "0-30"
    if age_days <= 60:
        return "31-60"
    if age_days <= 90:
        return "61-90"
    return "90+"


class LedgerService:

    # -------------------------------------------------------------------------
    # 0. Sequential Document Numbering
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_next_number(
        session: AsyncSession,
        tenant_id: str,
        doc_type: str,
        default_prefix: str,
        financial_year: str = "2026-27",
    ) -> str:
        """Fetch next sequential document number from NumberSeries or initialize."""
        stmt = select(NumberSeries).where(
            NumberSeries.tenant_id == tenant_id,
            NumberSeries.doc_type == doc_type,
            NumberSeries.financial_year == financial_year,
        )
        res = await session.execute(stmt)
        series = res.scalar_one_or_none()

        if not series:
            series = NumberSeries(
                tenant_id=tenant_id,
                doc_type=doc_type,
                financial_year=financial_year,
                prefix=default_prefix,
                current_number=1,
                range_start=1,
                range_end=999999,
            )
            session.add(series)
            num = 1
        else:
            series.current_number += 1
            num = series.current_number

        return f"{series.prefix}{num:04d}"

    # -------------------------------------------------------------------------
    # 1. Customer Payment Receipts & FIFO/Manual Allocations
    # -------------------------------------------------------------------------
    @staticmethod
    async def record_receipt_voucher(
        session: AsyncSession,
        tenant_id: str,
        payload: ReceiptVoucherCreateSchema,
    ) -> ReceiptVoucherResponseSchema:
        """Record customer payment receipt (full or partial), allocate to invoices, and update ledger."""
        party = await session.scalar(
            select(Party).where(Party.id == payload.party_id, Party.tenant_id == tenant_id)
        )
        if not party:
            raise ValueError(f"Customer party {payload.party_id} not found")

        voucher_number = await LedgerService.get_next_number(
            session=session,
            tenant_id=tenant_id,
            doc_type="PAYMENT_RECEIPT",
            default_prefix="REC/26-27/",
        )

        voucher_date = payload.voucher_date or today_ist()
        receipt_entry_id = str(uuid.uuid4())

        # 1. Post Credit Ledger Entry (strictly append-only)
        receipt_entry = LedgerEntry(
            id=receipt_entry_id,
            tenant_id=tenant_id,
            party_id=party.id,
            entry_type="PAYMENT_RECEIPT",
            debit_amount=Decimal("0.00"),
            credit_amount=payload.total_amount,
            reference_doc_type="RECEIPT_VOUCHER",
            reference_doc_id=receipt_entry_id,
            reference_doc_number=voucher_number,
            entry_date=voucher_date,
            # Payment mode is always recorded in notes ("via CASH") - cash reconciliation relies on it
            notes=(
                f"{payload.notes} (via {payload.payment_mode.upper()})"
                if payload.notes
                else f"Payment receipt #{voucher_number} via {payload.payment_mode.upper()}"
            ),
        )
        session.add(receipt_entry)

        # 2. Allocations
        allocation_details: List[AllocationDetailSchema] = []
        total_allocated = Decimal("0.00")

        if payload.allocation_method == "OLDEST_FIRST":
            # Fetch all debit entries for this party ordered by entry_date ASC (FIFO)
            debit_stmt = (
                select(LedgerEntry)
                .where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.party_id == party.id,
                    LedgerEntry.debit_amount > 0,
                    LedgerEntry.entry_type.not_in(SUPPLIER_ENTRY_TYPES),
                )
                .order_by(LedgerEntry.entry_date.asc(), LedgerEntry.created_at.asc())
            )
            debit_entries = (await session.execute(debit_stmt)).scalars().all()

            remaining_unallocated = payload.total_amount

            for deb in debit_entries:
                if remaining_unallocated <= Decimal("0.00"):
                    break

                # Sum already allocated to this debit invoice
                alloc_sum_stmt = select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), Decimal("0"))).where(
                    PaymentAllocation.tenant_id == tenant_id,
                    PaymentAllocation.invoice_entry_id == deb.id,
                )
                already_allocated = await session.scalar(alloc_sum_stmt) or Decimal("0")
                open_due = max(Decimal("0.00"), deb.debit_amount - already_allocated)

                if open_due > Decimal("0.00"):
                    settle_amt = min(remaining_unallocated, open_due).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                    alloc_id = str(uuid.uuid4())
                    alloc_record = PaymentAllocation(
                        id=alloc_id,
                        tenant_id=tenant_id,
                        payment_entry_id=receipt_entry_id,
                        invoice_entry_id=deb.id,
                        allocated_amount=settle_amt,
                    )
                    session.add(alloc_record)

                    allocation_details.append(
                        AllocationDetailSchema(
                            allocation_id=alloc_id,
                            invoice_entry_id=deb.id,
                            invoice_number=deb.reference_doc_number,
                            allocated_amount=settle_amt,
                        )
                    )

                    total_allocated += settle_amt
                    remaining_unallocated -= settle_amt

        elif payload.allocation_method == "MANUAL" and payload.manual_allocations:
            remaining_unallocated = payload.total_amount
            for item in payload.manual_allocations:
                if remaining_unallocated <= Decimal("0.00"):
                    break

                deb = await session.scalar(
                    select(LedgerEntry).where(
                        LedgerEntry.id == item.invoice_entry_id,
                        LedgerEntry.party_id == party.id,
                        LedgerEntry.tenant_id == tenant_id,
                    )
                )
                if not deb or deb.debit_amount <= Decimal("0.00"):
                    continue

                alloc_sum_stmt = select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), Decimal("0"))).where(
                    PaymentAllocation.tenant_id == tenant_id,
                    PaymentAllocation.invoice_entry_id == deb.id,
                )
                already_allocated = await session.scalar(alloc_sum_stmt) or Decimal("0")
                open_due = max(Decimal("0.00"), deb.debit_amount - already_allocated)

                settle_amt = min(item.amount, open_due, remaining_unallocated).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                if settle_amt > Decimal("0.00"):
                    alloc_id = str(uuid.uuid4())
                    alloc_record = PaymentAllocation(
                        id=alloc_id,
                        tenant_id=tenant_id,
                        payment_entry_id=receipt_entry_id,
                        invoice_entry_id=deb.id,
                        allocated_amount=settle_amt,
                    )
                    session.add(alloc_record)

                    allocation_details.append(
                        AllocationDetailSchema(
                            allocation_id=alloc_id,
                            invoice_entry_id=deb.id,
                            invoice_number=deb.reference_doc_number,
                            allocated_amount=settle_amt,
                        )
                    )

                    total_allocated += settle_amt
                    remaining_unallocated -= settle_amt

        # 3. Update party balance (balance reduces when customer pays)
        party.current_balance -= payload.total_amount
        unallocated_amt = payload.total_amount - total_allocated

        await session.commit()

        return ReceiptVoucherResponseSchema(
            id=receipt_entry_id,
            party_id=party.id,
            party_name=party.name,
            voucher_number=voucher_number,
            voucher_date=voucher_date,
            payment_mode=payload.payment_mode,
            reference_number=payload.reference_number,
            total_amount=payload.total_amount,
            allocated_amount=total_allocated,
            unallocated_amount=unallocated_amt,
            party_current_balance=party.current_balance,
            allocations=allocation_details,
            notes=payload.notes,
        )

    # -------------------------------------------------------------------------
    # 2. Supplier Payments
    # -------------------------------------------------------------------------
    @staticmethod
    async def record_supplier_payment(
        session: AsyncSession,
        tenant_id: str,
        payload: SupplierPaymentCreateSchema,
    ) -> SupplierPaymentResponseSchema:
        """Record payment made to supplier: debits supplier ledger and reduces payable balance."""
        supplier = await session.scalar(
            select(Party).where(Party.id == payload.supplier_id, Party.tenant_id == tenant_id)
        )
        if not supplier:
            raise ValueError(f"Supplier party {payload.supplier_id} not found")

        voucher_number = await LedgerService.get_next_number(
            session=session,
            tenant_id=tenant_id,
            doc_type="SUPPLIER_PAYMENT",
            default_prefix="PAY/26-27/",
        )

        voucher_date = payload.payment_date or today_ist()
        entry_id = str(uuid.uuid4())

        # Post Debit Ledger Entry (paying supplier debits their account, reducing negative balance)
        debit_entry = LedgerEntry(
            id=entry_id,
            tenant_id=tenant_id,
            party_id=supplier.id,
            entry_type="SUPPLIER_PAYMENT",
            debit_amount=payload.amount,
            credit_amount=Decimal("0.00"),
            reference_doc_type="SUPPLIER_PAYMENT",
            reference_doc_id=entry_id,
            reference_doc_number=voucher_number,
            entry_date=voucher_date,
            notes=(
                f"{payload.notes} (via {payload.payment_mode.upper()})"
                if payload.notes
                else f"Supplier payment #{voucher_number} via {payload.payment_mode.upper()}"
            ),
        )
        session.add(debit_entry)

        # Update supplier balance: adding debit amount reduces net payable
        supplier.current_balance += payload.amount

        await session.commit()

        return SupplierPaymentResponseSchema(
            id=entry_id,
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            voucher_number=voucher_number,
            payment_date=voucher_date,
            payment_mode=payload.payment_mode,
            reference_number=payload.reference_number,
            amount=payload.amount,
            supplier_current_balance=supplier.current_balance,
            notes=payload.notes,
        )

    # -------------------------------------------------------------------------
    # 3. Invoice-Wise Dues & Ageing Buckets
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_party_open_dues(
        session: AsyncSession,
        tenant_id: str,
        party_id: str,
        as_of_date: Optional[date] = None,
        side: Optional[str] = None,
    ) -> List[InvoiceDueItemSchema]:
        """Fetch all unpaid or partially paid bills with days overdue and ageing buckets.

        side='RECEIVABLE' (default for customers): sales-side debit entries, settled via PaymentAllocation.
        side='PAYABLE' (default for suppliers): purchase bills / credit opening balances, settled by
        supplier payments (debits) applied oldest bill first.
        """
        if not as_of_date:
            as_of_date = today_ist()

        party = await session.scalar(
            select(Party).where(Party.id == party_id, Party.tenant_id == tenant_id)
        )
        if not party:
            raise ValueError(f"Party {party_id} not found")

        if (side or default_side(party)) == "PAYABLE":
            return await LedgerService._get_supplier_open_bills(session, tenant_id, party, as_of_date)

        debit_stmt = (
            select(LedgerEntry)
            .where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.party_id == party_id,
                LedgerEntry.debit_amount > 0,
                LedgerEntry.entry_type.not_in(SUPPLIER_ENTRY_TYPES),
            )
            .order_by(LedgerEntry.entry_date.asc(), LedgerEntry.created_at.asc())
        )
        debit_entries = (await session.execute(debit_stmt)).scalars().all()

        results: List[InvoiceDueItemSchema] = []

        for deb in debit_entries:
            alloc_sum_stmt = select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), Decimal("0"))).where(
                PaymentAllocation.tenant_id == tenant_id,
                PaymentAllocation.invoice_entry_id == deb.id,
            )
            already_allocated = await session.scalar(alloc_sum_stmt) or Decimal("0")
            due_amt = max(Decimal("0.00"), deb.debit_amount - already_allocated).quantize(TWO_PLACES)

            if due_amt > Decimal("0.00"):
                age_days = (as_of_date - deb.entry_date).days
                if age_days <= 30:
                    bucket = "0-30"
                elif age_days <= 60:
                    bucket = "31-60"
                elif age_days <= 90:
                    bucket = "61-90"
                else:
                    bucket = "90+"

                is_overdue = age_days > party.credit_days

                results.append(
                    InvoiceDueItemSchema(
                        entry_id=deb.id,
                        doc_type=deb.entry_type,
                        doc_number=deb.reference_doc_number,
                        doc_date=deb.entry_date,
                        total_amount=deb.debit_amount,
                        allocated_amount=already_allocated,
                        due_amount=due_amt,
                        age_days=age_days,
                        bucket=bucket,
                        is_overdue=is_overdue,
                    )
                )

        return results

    @staticmethod
    async def _supplier_payable_totals(
        session: AsyncSession, tenant_id: str, party: Party
    ) -> Tuple[List[LedgerEntry], Decimal]:
        """Supplier bills (credit entries, oldest first) and the total paid to the supplier (debits).

        For a 'BOTH' party only supplier documents count (its customer-side entries are receivables).
        """
        bill_filters = [
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.party_id == party.id,
            LedgerEntry.credit_amount > 0,
        ]
        paid_filters = [
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.party_id == party.id,
            LedgerEntry.debit_amount > 0,
        ]
        if party.party_type == "BOTH":
            bill_filters.append(LedgerEntry.entry_type == "PURCHASE_BILL")
            paid_filters.append(LedgerEntry.entry_type == "SUPPLIER_PAYMENT")
        bills = (
            await session.execute(
                select(LedgerEntry)
                .where(*bill_filters)
                .order_by(LedgerEntry.entry_date.asc(), LedgerEntry.created_at.asc())
            )
        ).scalars().all()
        total_paid = await session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.debit_amount), Decimal("0"))).where(*paid_filters)
        ) or Decimal("0.00")
        return list(bills), Decimal(total_paid)

    @staticmethod
    async def _get_supplier_open_bills(
        session: AsyncSession,
        tenant_id: str,
        party: Party,
        as_of_date: date,
    ) -> List[InvoiceDueItemSchema]:
        """Open purchase bills for a supplier: payments settle the oldest bills first (FIFO)."""
        bills, total_paid = await LedgerService._supplier_payable_totals(session, tenant_id, party)
        remaining_paid = total_paid
        results: List[InvoiceDueItemSchema] = []
        for bill in bills:
            settled = min(remaining_paid, bill.credit_amount)
            remaining_paid -= settled
            due_amt = (bill.credit_amount - settled).quantize(TWO_PLACES)
            if due_amt <= Decimal("0.00"):
                continue
            age_days = (as_of_date - bill.entry_date).days
            results.append(
                InvoiceDueItemSchema(
                    entry_id=bill.id,
                    doc_type=bill.entry_type,
                    doc_number=bill.reference_doc_number,
                    doc_date=bill.entry_date,
                    total_amount=bill.credit_amount,
                    allocated_amount=settled.quantize(TWO_PLACES),
                    due_amount=due_amt,
                    age_days=age_days,
                    bucket=_bucket(age_days),
                    is_overdue=age_days > party.credit_days,
                )
            )
        return results

    @staticmethod
    async def get_party_ageing_summary(
        session: AsyncSession,
        tenant_id: str,
        party_id: str,
        as_of_date: Optional[date] = None,
        side: Optional[str] = None,
    ) -> PartyAgeingSummarySchema:
        """Calculate complete ageing buckets, overdue totals, and credit limit compliance."""
        if not as_of_date:
            as_of_date = today_ist()

        party = await session.scalar(
            select(Party).where(Party.id == party_id, Party.tenant_id == tenant_id)
        )
        if not party:
            raise ValueError(f"Party {party_id} not found")

        side = side or default_side(party)
        open_dues = await LedgerService.get_party_open_dues(
            session=session,
            tenant_id=tenant_id,
            party_id=party_id,
            as_of_date=as_of_date,
            side=side,
        )

        b_0_30 = Decimal("0.00")
        b_31_60 = Decimal("0.00")
        b_61_90 = Decimal("0.00")
        b_90_plus = Decimal("0.00")
        total_overdue = Decimal("0.00")

        for item in open_dues:
            if item.bucket == "0-30":
                b_0_30 += item.due_amount
            elif item.bucket == "31-60":
                b_31_60 += item.due_amount
            elif item.bucket == "61-90":
                b_61_90 += item.due_amount
            else:
                b_90_plus += item.due_amount

            if item.is_overdue:
                total_overdue += item.due_amount

        if side == "PAYABLE":
            bills, total_paid = await LedgerService._supplier_payable_totals(session, tenant_id, party)
            total_billed = sum((b.credit_amount for b in bills), Decimal("0.00"))
            return PartyAgeingSummarySchema(
                party_id=party.id,
                party_name=party.name,
                phone=party.phone,
                side="PAYABLE",
                credit_limit=party.credit_limit,
                credit_days=party.credit_days,
                current_balance=party.current_balance,
                is_credit_exceeded=False,
                bucket_0_30=b_0_30,
                bucket_31_60=b_31_60,
                bucket_61_90=b_61_90,
                bucket_90_plus=b_90_plus,
                total_overdue=total_overdue,
                # Paid to the supplier beyond all bills = advance with the supplier
                unallocated_advance=max(Decimal("0.00"), total_paid - total_billed).quantize(TWO_PLACES),
                open_invoices=open_dues,
            )

        # Compute unallocated advances for this party
        total_credits = await session.scalar(
            select(func.coalesce(func.sum(LedgerEntry.credit_amount), Decimal("0"))).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.party_id == party_id,
                LedgerEntry.credit_amount > 0,
                LedgerEntry.entry_type.not_in(SUPPLIER_ENTRY_TYPES),
            )
        ) or Decimal("0.00")

        # Total allocations originating from this party's credit payments
        party_payment_ids = select(LedgerEntry.id).where(
            LedgerEntry.tenant_id == tenant_id,
            LedgerEntry.party_id == party_id,
            LedgerEntry.credit_amount > 0,
            LedgerEntry.entry_type.not_in(SUPPLIER_ENTRY_TYPES),
        )
        total_allocated = await session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), Decimal("0"))).where(
                PaymentAllocation.tenant_id == tenant_id,
                PaymentAllocation.payment_entry_id.in_(party_payment_ids),
            )
        ) or Decimal("0.00")

        unallocated_advance = max(Decimal("0.00"), total_credits - total_allocated).quantize(TWO_PLACES)
        is_exceeded = bool(party.credit_limit > 0 and party.current_balance > party.credit_limit)

        return PartyAgeingSummarySchema(
            party_id=party.id,
            party_name=party.name,
            phone=party.phone,
            side="RECEIVABLE",
            credit_limit=party.credit_limit,
            credit_days=party.credit_days,
            current_balance=party.current_balance,
            is_credit_exceeded=is_exceeded,
            bucket_0_30=b_0_30,
            bucket_31_60=b_31_60,
            bucket_61_90=b_61_90,
            bucket_90_plus=b_90_plus,
            total_overdue=total_overdue,
            unallocated_advance=unallocated_advance,
            open_invoices=open_dues,
        )

    # -------------------------------------------------------------------------
    # 4. Supplier Balances Summary
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_supplier_balances_summary(
        session: AsyncSession,
        tenant_id: str,
    ) -> SupplierBalancesSummaryResponseSchema:
        """Aggregate total purchases, payments made, and net payables for all suppliers."""
        stmt = (
            select(Party)
            .where(
                Party.tenant_id == tenant_id,
                Party.is_active.is_(True),
                or_(Party.party_type == "SUPPLIER", Party.party_type == "BOTH"),
            )
            .order_by(Party.name.asc())
        )
        suppliers = (await session.execute(stmt)).scalars().all()

        supplier_items: List[SupplierBalanceItemSchema] = []
        total_payable = Decimal("0.00")

        for s in suppliers:
            # Sum total purchase credits
            purchases = await session.scalar(
                select(func.coalesce(func.sum(LedgerEntry.credit_amount), Decimal("0"))).where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.party_id == s.id,
                    LedgerEntry.entry_type == "PURCHASE_BILL",
                )
            ) or Decimal("0.00")

            # Sum total payments debits
            payments = await session.scalar(
                select(func.coalesce(func.sum(LedgerEntry.debit_amount), Decimal("0"))).where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.party_id == s.id,
                    LedgerEntry.entry_type == "SUPPLIER_PAYMENT",
                )
            ) or Decimal("0.00")

            # Net payable: in double-entry supplier balance is negative when we owe them
            net_owe = max(Decimal("0.00"), -s.current_balance).quantize(TWO_PLACES)
            total_payable += net_owe

            # Last transaction date
            last_dt = await session.scalar(
                select(func.max(LedgerEntry.entry_date)).where(
                    LedgerEntry.tenant_id == tenant_id,
                    LedgerEntry.party_id == s.id,
                )
            )

            supplier_items.append(
                SupplierBalanceItemSchema(
                    supplier_id=s.id,
                    name=s.name,
                    phone=s.phone,
                    gstin=s.gstin,
                    total_purchases=purchases,
                    total_paid=payments,
                    current_balance=s.current_balance,
                    net_payable=net_owe,
                    last_transaction_date=last_dt,
                )
            )

        return SupplierBalancesSummaryResponseSchema(
            total_suppliers=len(supplier_items),
            total_payable_amount=total_payable,
            suppliers=supplier_items,
        )

    # -------------------------------------------------------------------------
    # 5. WhatsApp Collection Reminders & Call List
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_collection_call_list(
        session: AsyncSession,
        tenant_id: str,
        min_days_overdue: int = 0,
        min_amount: Decimal = Decimal("0.00"),
    ) -> List[CollectionReminderItemSchema]:
        """Ranked owner morning call list prioritized by Overdue Amount * sqrt(Days Overdue)."""
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
        shop_name = tenant.business_name if tenant else "Sri Murugan Hardware"
        shop_vpa = "store@icici"

        # Query all customer parties with positive balance
        stmt = (
            select(Party)
            .where(
                Party.tenant_id == tenant_id,
                Party.is_active.is_(True),
                Party.current_balance > min_amount,
                or_(Party.party_type == "CUSTOMER", Party.party_type == "BOTH"),
            )
        )
        parties = (await session.execute(stmt)).scalars().all()

        reminders: List[CollectionReminderItemSchema] = []
        today = today_ist()

        for p in parties:
            open_dues = await LedgerService.get_party_open_dues(
                session=session,
                tenant_id=tenant_id,
                party_id=p.id,
                as_of_date=today,
            )

            overdue_bills = [inv for inv in open_dues if inv.is_overdue]
            if not overdue_bills:
                continue  # nothing is past its credit period yet: not on the call list

            # Oldest overdue bill (dues are sorted by date ASC) and the amount actually overdue,
            # net of any unallocated advance (never more than what the party owes overall)
            oldest_inv = overdue_bills[0]
            days_overdue = max(0, oldest_inv.age_days - p.credit_days)

            overdue_amount = min(
                sum((inv.due_amount for inv in overdue_bills), Decimal("0.00")),
                p.current_balance,
            ).quantize(TWO_PLACES)
            if overdue_amount <= Decimal("0.00"):
                continue

            if days_overdue < min_days_overdue:
                continue

            # Urgency Score: Overdue Amount * sqrt(max(1, days_overdue))
            sqrt_days = Decimal(str(round(math.sqrt(max(1, days_overdue)), 4)))
            urgency_score = (overdue_amount * sqrt_days).quantize(TWO_PLACES)

            # Formulate UPI intent link
            upi_link = ThermalReceiptGenerator.generate_upi_qr_string(
                vpa=shop_vpa,
                payee_name=shop_name,
                amount=p.current_balance,
                invoice_number=oldest_inv.doc_number,
            )

            # Formulate Bilingual WhatsApp Reminder Message
            msg = (
                f"வணக்கம் {p.name},\n"
                f"{shop_name} கணக்கில் தங்களின் நிலுவைத் தொகை ₹{p.current_balance:,.2f}.\n"
                f"பில் எண் {oldest_inv.doc_number} ({oldest_inv.doc_date.strftime('%d-%b-%Y')}) "
                f"{days_overdue} நாட்களாக நிலுவையில் உள்ளது.\n\n"
                f"உடனடி UPI மூலம் செலுத்தவும்: {upi_link}\n"
                f"நன்றி, {shop_name}"
            )

            reminders.append(
                CollectionReminderItemSchema(
                    party_id=p.id,
                    customer_name=p.name,
                    phone=p.phone,
                    current_balance=p.current_balance,
                    credit_limit=p.credit_limit,
                    credit_days=p.credit_days,
                    oldest_bill_number=oldest_inv.doc_number,
                    oldest_bill_date=oldest_inv.doc_date,
                    days_overdue=days_overdue,
                    overdue_amount=overdue_amount,
                    urgency_score=urgency_score,
                    whatsapp_message=msg,
                    upi_payment_link=upi_link,
                )
            )

        # Sort descending by urgency score
        reminders.sort(key=lambda r: r.urgency_score, reverse=True)
        return reminders

    @staticmethod
    async def dispatch_whatsapp_reminder(
        session: AsyncSession,
        tenant_id: str,
        payload: DispatchReminderRequestSchema,
    ) -> DispatchReminderResponseSchema:
        """Dispatch or simulate WhatsApp payment reminder and log in collection_reminder_logs."""
        party = await session.scalar(
            select(Party).where(Party.id == payload.party_id, Party.tenant_id == tenant_id)
        )
        if not party:
            raise ValueError(f"Party {payload.party_id} not found")

        phone = payload.phone_override or party.phone or "9876543210"

        # Generate reminder details
        call_items = await LedgerService.get_collection_call_list(
            session=session,
            tenant_id=tenant_id,
            min_days_overdue=0,
            min_amount=Decimal("0.00"),
        )
        matched_item = next((item for item in call_items if item.party_id == party.id), None)

        if matched_item:
            msg_text = matched_item.whatsapp_message
            upi_link = matched_item.upi_payment_link
        else:
            upi_link = f"upi://pay?pa=store@icici&pn=HardwareStore&am={party.current_balance}&cu=INR"
            msg_text = (
                f"வணக்கம் {party.name},\n"
                f"தங்களின் நிலுவைத் தொகை ₹{party.current_balance:,.2f}.\n"
                f"UPI மூலம் செலுத்த: {upi_link}"
            )

        if payload.custom_note:
            msg_text += f"\nகுறிப்பு: {payload.custom_note}"

        log_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        log = CollectionReminderLog(
            id=log_id,
            tenant_id=tenant_id,
            party_id=party.id,
            recipient_phone=phone,
            message_text=msg_text,
            upi_payment_link=upi_link,
            status="SENT",
            dispatched_at=now,
        )
        session.add(log)
        await session.commit()

        return DispatchReminderResponseSchema(
            log_id=log_id,
            party_id=party.id,
            recipient_phone=phone,
            message_text=msg_text,
            upi_link=upi_link,
            status="SENT",
            dispatched_at=now,
        )
