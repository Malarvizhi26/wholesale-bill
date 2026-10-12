"""Party Ledger & FIFO Payment Allocation Engine.

Invariants (per Module 3 of Development Plan):
1. ledger_entries is strictly append-only. No updates or deletes on posted entries.
2. Current Balance = Opening Balance + SUM(Debits) - SUM(Credits).
3. Payment allocations settle oldest invoices first (FIFO) unless manual override.
4. Ageing buckets: 0-30, 31-60, 61-90, 90+ days.
5. Paisa integrity: party.current_balance == SUM(unpaid invoices) - SUM(unallocated advances).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Tuple

from app.core.timeutils import today_ist

TWO_PLACES = Decimal("0.01")


@dataclass
class LedgerEntry:
    """Represents one immutable row in the ledger_entries table."""
    entry_id: str
    party_id: str
    entry_type: str  # 'SALES_INVOICE', 'PAYMENT_RECEIPT', 'SALES_RETURN_CREDIT_NOTE', etc.
    debit_amount: Decimal = Decimal("0.00")
    credit_amount: Decimal = Decimal("0.00")
    reference_doc_number: str = ""
    entry_date: date = field(default_factory=today_ist)


@dataclass
class PaymentAllocation:
    """Links a payment (credit entry) to a specific invoice (debit entry)."""
    payment_entry_id: str
    invoice_entry_id: str
    allocated_amount: Decimal


@dataclass
class AgeingBucket:
    current_0_30: Decimal = Decimal("0.00")
    days_31_60: Decimal = Decimal("0.00")
    days_61_90: Decimal = Decimal("0.00")
    days_90_plus: Decimal = Decimal("0.00")

    @property
    def total(self) -> Decimal:
        return self.current_0_30 + self.days_31_60 + self.days_61_90 + self.days_90_plus


class PartyLedgerEngine:
    """In-memory ledger engine for testing and offline calculation."""

    def __init__(self, party_id: str, opening_balance: Decimal = Decimal("0.00")):
        self.party_id = party_id
        self.opening_balance = opening_balance
        self.entries: List[LedgerEntry] = []
        self.allocations: List[PaymentAllocation] = []

    @property
    def current_balance(self) -> Decimal:
        """Current Balance = Opening + SUM(Debits) - SUM(Credits)."""
        total_debit = sum((e.debit_amount for e in self.entries), Decimal("0.00"))
        total_credit = sum((e.credit_amount for e in self.entries), Decimal("0.00"))
        return (self.opening_balance + total_debit - total_credit).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    def post_invoice(self, entry: LedgerEntry) -> None:
        """Post a sales invoice (debit) to the ledger. Append-only."""
        assert entry.debit_amount > 0, "Invoice must have a positive debit amount"
        assert entry.credit_amount == Decimal("0.00"), "Invoice debit entry must not have credit"
        self.entries.append(entry)

    def post_credit_note(self, entry: LedgerEntry) -> None:
        """Post a sales return credit note. Append-only."""
        assert entry.credit_amount > 0, "Credit note must have positive credit amount"
        assert entry.debit_amount == Decimal("0.00"), "Credit note must not have debit"
        self.entries.append(entry)

    def get_invoice_outstanding(self, invoice_entry_id: str) -> Decimal:
        """How much is still unpaid on a specific invoice."""
        entry = next((e for e in self.entries if e.entry_id == invoice_entry_id), None)
        if entry is None or entry.debit_amount == Decimal("0.00"):
            return Decimal("0.00")

        allocated = sum(
            (a.allocated_amount for a in self.allocations if a.invoice_entry_id == invoice_entry_id),
            Decimal("0.00"),
        )
        return max(Decimal("0.00"), entry.debit_amount - allocated).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    def get_open_invoices(self) -> List[Tuple[LedgerEntry, Decimal]]:
        """Return all invoices with outstanding > 0, sorted by date ASC (oldest first)."""
        results = []
        for entry in self.entries:
            if entry.debit_amount > 0:
                outstanding = self.get_invoice_outstanding(entry.entry_id)
                if outstanding > 0:
                    results.append((entry, outstanding))
        results.sort(key=lambda x: x[0].entry_date)
        return results

    def receive_payment_fifo(self, payment_entry: LedgerEntry) -> List[PaymentAllocation]:
        """Receive a payment and auto-allocate oldest-first (FIFO).

        Returns the list of allocations created.
        """
        assert payment_entry.credit_amount > 0, "Payment must have positive credit amount"
        self.entries.append(payment_entry)

        remaining = payment_entry.credit_amount
        new_allocations: List[PaymentAllocation] = []

        for invoice_entry, outstanding in self.get_open_invoices():
            if remaining <= Decimal("0.00"):
                break

            settle_amount = min(remaining, outstanding).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            alloc = PaymentAllocation(
                payment_entry_id=payment_entry.entry_id,
                invoice_entry_id=invoice_entry.entry_id,
                allocated_amount=settle_amount,
            )
            self.allocations.append(alloc)
            new_allocations.append(alloc)
            remaining -= settle_amount

        # Any remaining amount is "on account" (unallocated advance)
        return new_allocations

    def receive_payment_manual(
        self,
        payment_entry: LedgerEntry,
        manual_allocations: List[Tuple[str, Decimal]],
    ) -> List[PaymentAllocation]:
        """Receive a payment with manual invoice allocation.

        manual_allocations: list of (invoice_entry_id, amount) tuples.
        """
        assert payment_entry.credit_amount > 0
        total_allocated = sum((amt for _, amt in manual_allocations), Decimal("0.00"))
        assert total_allocated <= payment_entry.credit_amount, (
            f"Manual allocations ({total_allocated}) exceed payment amount ({payment_entry.credit_amount})"
        )

        self.entries.append(payment_entry)

        new_allocations: List[PaymentAllocation] = []
        for inv_id, amount in manual_allocations:
            outstanding = self.get_invoice_outstanding(inv_id)
            settle = min(amount, outstanding).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if settle > 0:
                alloc = PaymentAllocation(
                    payment_entry_id=payment_entry.entry_id,
                    invoice_entry_id=inv_id,
                    allocated_amount=settle,
                )
                self.allocations.append(alloc)
                new_allocations.append(alloc)

        return new_allocations

    def get_unallocated_advance(self) -> Decimal:
        """Total payment credits not yet allocated to any invoice."""
        total_credits = sum(
            (e.credit_amount for e in self.entries if e.credit_amount > 0),
            Decimal("0.00"),
        )
        total_allocated = sum(
            (a.allocated_amount for a in self.allocations),
            Decimal("0.00"),
        )
        return max(Decimal("0.00"), total_credits - total_allocated).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    def get_sum_unpaid_invoices(self) -> Decimal:
        """Sum of all outstanding invoice amounts."""
        return sum(
            (outstanding for _, outstanding in self.get_open_invoices()),
            Decimal("0.00"),
        ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def verify_paisa_integrity(self) -> Decimal:
        """The golden invariant: current_balance == sum_unpaid - unallocated_advance.

        Returns the discrepancy (should be 0.00).
        """
        expected = self.get_sum_unpaid_invoices() - self.get_unallocated_advance()
        return (self.current_balance - expected).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    def calculate_ageing(self, as_of_date: Optional[date] = None) -> AgeingBucket:
        """Classify outstanding invoices into ageing buckets."""
        if as_of_date is None:
            as_of_date = today_ist()

        bucket = AgeingBucket()
        for entry, outstanding in self.get_open_invoices():
            age_days = (as_of_date - entry.entry_date).days
            if age_days <= 30:
                bucket.current_0_30 += outstanding
            elif age_days <= 60:
                bucket.days_31_60 += outstanding
            elif age_days <= 90:
                bucket.days_61_90 += outstanding
            else:
                bucket.days_90_plus += outstanding

        return bucket
