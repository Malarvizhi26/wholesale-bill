"""Golden-file tests for Party Ledger & FIFO Payment Allocation Engine.

These tests verify the core invariants from Module 3 of Development Plan:
1. Current Balance = Opening + SUM(Debits) - SUM(Credits).
2. FIFO auto-allocation settles oldest invoices first.
3. Ageing buckets classify correctly by day count.
4. Paisa integrity: current_balance == sum_unpaid_invoices - unallocated_advances.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.modules.ledger.ledger_engine import (
    PartyLedgerEngine,
    LedgerEntry,
)


# ─── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def empty_ledger():
    return PartyLedgerEngine(party_id="party-001", opening_balance=Decimal("0.00"))


@pytest.fixture
def ledger_with_opening():
    return PartyLedgerEngine(party_id="party-002", opening_balance=Decimal("5000.00"))


@pytest.fixture
def ledger_with_two_invoices():
    """Ledger with Bill 1 (₹2500 on Sep 1) and Bill 2 (₹4000 on Sep 10)."""
    ledger = PartyLedgerEngine(party_id="party-003", opening_balance=Decimal("0.00"))
    ledger.post_invoice(LedgerEntry(
        entry_id="inv-001",
        party_id="party-003",
        entry_type="SALES_INVOICE",
        debit_amount=Decimal("2500.00"),
        reference_doc_number="INV/26-27/0001",
        entry_date=date(2026, 9, 1),
    ))
    ledger.post_invoice(LedgerEntry(
        entry_id="inv-002",
        party_id="party-003",
        entry_type="SALES_INVOICE",
        debit_amount=Decimal("4000.00"),
        reference_doc_number="INV/26-27/0002",
        entry_date=date(2026, 9, 10),
    ))
    return ledger


# ─── Test: Balance Calculation ───────────────────────────────────────
class TestBalanceCalculation:
    def test_empty_ledger_zero_balance(self, empty_ledger):
        assert empty_ledger.current_balance == Decimal("0.00")

    def test_opening_balance(self, ledger_with_opening):
        assert ledger_with_opening.current_balance == Decimal("5000.00")

    def test_invoice_increases_balance(self, empty_ledger):
        empty_ledger.post_invoice(LedgerEntry(
            entry_id="inv-100",
            party_id="party-001",
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("1500.50"),
            reference_doc_number="INV/001",
        ))
        assert empty_ledger.current_balance == Decimal("1500.50")

    def test_payment_decreases_balance(self, ledger_with_two_invoices):
        ledger_with_two_invoices.receive_payment_fifo(LedgerEntry(
            entry_id="pay-001",
            party_id="party-003",
            entry_type="PAYMENT_RECEIPT",
            credit_amount=Decimal("1000.00"),
            reference_doc_number="REC/001",
        ))
        assert ledger_with_two_invoices.current_balance == Decimal("5500.00")


# ─── Test: FIFO Allocation ──────────────────────────────────────────
class TestFIFOAllocation:
    def test_fifo_settles_oldest_first(self, ledger_with_two_invoices):
        """Receipt of ₹3000: Bill 1 (₹2500) fully settled, Bill 2 gets ₹500."""
        allocations = ledger_with_two_invoices.receive_payment_fifo(LedgerEntry(
            entry_id="pay-001",
            party_id="party-003",
            entry_type="PAYMENT_RECEIPT",
            credit_amount=Decimal("3000.00"),
            reference_doc_number="REC/001",
            entry_date=date(2026, 10, 1),
        ))

        assert len(allocations) == 2

        # Bill 1 fully settled
        assert allocations[0].invoice_entry_id == "inv-001"
        assert allocations[0].allocated_amount == Decimal("2500.00")

        # Bill 2 partially settled
        assert allocations[1].invoice_entry_id == "inv-002"
        assert allocations[1].allocated_amount == Decimal("500.00")

        # Outstanding check
        assert ledger_with_two_invoices.get_invoice_outstanding("inv-001") == Decimal("0.00")
        assert ledger_with_two_invoices.get_invoice_outstanding("inv-002") == Decimal("3500.00")

    def test_overpayment_creates_advance(self, ledger_with_two_invoices):
        """Payment of ₹8000 against ₹6500 dues -> ₹1500 unallocated advance."""
        ledger_with_two_invoices.receive_payment_fifo(LedgerEntry(
            entry_id="pay-big",
            party_id="party-003",
            entry_type="PAYMENT_RECEIPT",
            credit_amount=Decimal("8000.00"),
            reference_doc_number="REC/002",
        ))

        assert ledger_with_two_invoices.get_invoice_outstanding("inv-001") == Decimal("0.00")
        assert ledger_with_two_invoices.get_invoice_outstanding("inv-002") == Decimal("0.00")
        assert ledger_with_two_invoices.get_unallocated_advance() == Decimal("1500.00")
        assert ledger_with_two_invoices.current_balance == Decimal("-1500.00")

    def test_exact_payment_clears_all(self, ledger_with_two_invoices):
        """Pay exactly ₹6500 -> both invoices settled, zero advance, zero balance."""
        ledger_with_two_invoices.receive_payment_fifo(LedgerEntry(
            entry_id="pay-exact",
            party_id="party-003",
            entry_type="PAYMENT_RECEIPT",
            credit_amount=Decimal("6500.00"),
            reference_doc_number="REC/003",
        ))

        assert ledger_with_two_invoices.get_sum_unpaid_invoices() == Decimal("0.00")
        assert ledger_with_two_invoices.get_unallocated_advance() == Decimal("0.00")
        assert ledger_with_two_invoices.current_balance == Decimal("0.00")


# ─── Test: Manual Allocation ────────────────────────────────────────
class TestManualAllocation:
    def test_manual_allocation_specific_invoice(self, ledger_with_two_invoices):
        """Manually allocate ₹2000 to Bill 2 only, leaving Bill 1 untouched."""
        ledger_with_two_invoices.receive_payment_manual(
            payment_entry=LedgerEntry(
                entry_id="pay-manual",
                party_id="party-003",
                entry_type="PAYMENT_RECEIPT",
                credit_amount=Decimal("2000.00"),
                reference_doc_number="REC/004",
            ),
            manual_allocations=[("inv-002", Decimal("2000.00"))],
        )

        assert ledger_with_two_invoices.get_invoice_outstanding("inv-001") == Decimal("2500.00")
        assert ledger_with_two_invoices.get_invoice_outstanding("inv-002") == Decimal("2000.00")


# ─── Test: Paisa Integrity Invariant ────────────────────────────────
class TestPaisaIntegrity:
    def test_integrity_after_mixed_operations(self):
        """50 invoices and 20 partial payments with odd paisa values -> zero discrepancy."""
        ledger = PartyLedgerEngine(party_id="stress-test", opening_balance=Decimal("0.00"))

        # Post 50 invoices with varying odd amounts
        for i in range(1, 51):
            amount = Decimal(f"{100 + i * 37}.{(i * 13) % 100:02d}")
            ledger.post_invoice(LedgerEntry(
                entry_id=f"inv-{i:03d}",
                party_id="stress-test",
                entry_type="SALES_INVOICE",
                debit_amount=amount,
                reference_doc_number=f"INV/{i:03d}",
                entry_date=date(2026, 1, 1) + timedelta(days=i),
            ))

        # Post 20 partial payments
        for j in range(1, 21):
            pay_amount = Decimal(f"{50 + j * 23}.{(j * 17) % 100:02d}")
            ledger.receive_payment_fifo(LedgerEntry(
                entry_id=f"pay-{j:03d}",
                party_id="stress-test",
                entry_type="PAYMENT_RECEIPT",
                credit_amount=pay_amount,
                reference_doc_number=f"REC/{j:03d}",
                entry_date=date(2026, 6, 1) + timedelta(days=j),
            ))

        # THE GOLDEN INVARIANT: discrepancy must be exactly ₹0.00
        discrepancy = ledger.verify_paisa_integrity()
        assert discrepancy == Decimal("0.00"), f"Paisa integrity violated: discrepancy = {discrepancy}"


# ─── Test: Ageing Buckets ───────────────────────────────────────────
class TestAgeingBuckets:
    def test_ageing_classification(self):
        """Invoice on Day 0, check at Day 65 -> falls in 61-90 bucket."""
        ledger = PartyLedgerEngine(party_id="ageing-test", opening_balance=Decimal("0.00"))
        invoice_date = date(2026, 8, 1)
        check_date = date(2026, 10, 5)  # 65 days later

        ledger.post_invoice(LedgerEntry(
            entry_id="inv-age-1",
            party_id="ageing-test",
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("5000.00"),
            reference_doc_number="INV/AGE/001",
            entry_date=invoice_date,
        ))

        bucket = ledger.calculate_ageing(as_of_date=check_date)
        assert bucket.current_0_30 == Decimal("0.00")
        assert bucket.days_31_60 == Decimal("0.00")
        assert bucket.days_61_90 == Decimal("5000.00")
        assert bucket.days_90_plus == Decimal("0.00")

    def test_multiple_buckets(self):
        """Three invoices in different age ranges."""
        ledger = PartyLedgerEngine(party_id="multi-age", opening_balance=Decimal("0.00"))
        check_date = date(2026, 10, 1)

        # Invoice 1: 10 days old (0-30)
        ledger.post_invoice(LedgerEntry(
            entry_id="inv-a1", party_id="multi-age", entry_type="SALES_INVOICE",
            debit_amount=Decimal("1000.00"), reference_doc_number="A1",
            entry_date=date(2026, 9, 21),
        ))
        # Invoice 2: 45 days old (31-60)
        ledger.post_invoice(LedgerEntry(
            entry_id="inv-a2", party_id="multi-age", entry_type="SALES_INVOICE",
            debit_amount=Decimal("2000.00"), reference_doc_number="A2",
            entry_date=date(2026, 8, 17),
        ))
        # Invoice 3: 100 days old (90+)
        ledger.post_invoice(LedgerEntry(
            entry_id="inv-a3", party_id="multi-age", entry_type="SALES_INVOICE",
            debit_amount=Decimal("3000.00"), reference_doc_number="A3",
            entry_date=date(2026, 6, 23),
        ))

        bucket = ledger.calculate_ageing(as_of_date=check_date)
        assert bucket.current_0_30 == Decimal("1000.00")
        assert bucket.days_31_60 == Decimal("2000.00")
        assert bucket.days_61_90 == Decimal("0.00")
        assert bucket.days_90_plus == Decimal("3000.00")
        assert bucket.total == Decimal("6000.00")
