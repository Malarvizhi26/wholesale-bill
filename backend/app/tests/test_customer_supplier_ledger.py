"""Integration tests for Customer & Supplier Ledger Module.

Validates all 5 core requirements:
1. Credit limits (configuration, breach tracking, warning flags)
2. Partial payments (receipt vouchers with FIFO oldest-first and manual allocations, unallocated advances)
3. Invoice-wise dues (open balances per bill, days overdue, 4 ageing buckets: 0-30, 31-60, 61-90, 90+)
4. Supplier balances (purchases vs payments made, net payables)
5. Collection reminders (urgency score ranking, bilingual WhatsApp text, dynamic UPI QR links, dispatch log)
"""

from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_factory
from app.core.init_db import init_db, seed_demo_data
from app.models.ledger import Party, LedgerEntry, PaymentAllocation, CollectionReminderLog

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_credit_limit_configuration_and_breach():
    """Verify party credit limit configuration and breach detection."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Create a customer party with ₹5,000 credit limit and 15 credit days
        res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Ramu Builders",
                "phone": "9876543210",
                "credit_limit": "5000.00",
                "credit_days": 15,
                "opening_balance": "0.00",
            },
        )
        assert res.status_code == 201
        data = res.json()
        party_id = data["id"]
        assert Decimal(str(data["credit_limit"])) == Decimal("5000.00")
        assert data["credit_days"] == 15

        # 2. Initially balance is 0, credit limit is not exceeded
        ageing_res = await ac.get(f"/api/v1/ledger/parties/{party_id}/ageing", headers=headers)
        assert ageing_res.status_code == 200
        ageing = ageing_res.json()
        assert ageing["is_credit_exceeded"] is False
        assert Decimal(str(ageing["current_balance"])) == Decimal("0.00")

        # 3. Simulate invoice posting of ₹7,500 (exceeding ₹5,000 credit limit)
        async with async_session_factory() as session:
            party = await session.scalar(select(Party).where(Party.id == party_id))
            assert party is not None
            party.current_balance = Decimal("7500.00")

            inv_entry = LedgerEntry(
                id=str(uuid.uuid4()),
                tenant_id=DEMO_TENANT_ID,
                party_id=party_id,
                entry_type="SALES_INVOICE",
                debit_amount=Decimal("7500.00"),
                credit_amount=Decimal("0.00"),
                reference_doc_type="SALES_INVOICE",
                reference_doc_id=str(uuid.uuid4()),
                reference_doc_number="INV/26-27/9901",
                entry_date=date.today(),
                notes="Invoice exceeding credit limit",
            )
            session.add(inv_entry)
            await session.commit()

        # 4. Check ageing endpoint verifies credit limit breach
        ageing_res2 = await ac.get(f"/api/v1/ledger/parties/{party_id}/ageing", headers=headers)
        assert ageing_res2.status_code == 200
        ageing2 = ageing_res2.json()
        assert ageing2["is_credit_exceeded"] is True
        assert Decimal(str(ageing2["current_balance"])) == Decimal("7500.00")


@pytest.mark.asyncio
async def test_partial_payment_fifo_auto_allocation():
    """Verify receipt voucher with FIFO OLDEST_FIRST auto-allocation across multiple invoices."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    # Create customer
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Karthi Contractors",
                "phone": "9840123456",
                "credit_limit": "20000.00",
                "credit_days": 30,
            },
        )
        party_id = p_res.json()["id"]

    # Post two sales invoices: Bill 1 = ₹1,000 (10 days ago), Bill 2 = ₹2,000 (5 days ago)
    inv1_id = str(uuid.uuid4())
    inv2_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        party = await session.scalar(select(Party).where(Party.id == party_id))
        party.current_balance = Decimal("3000.00")

        inv1 = LedgerEntry(
            id=inv1_id,
            tenant_id=DEMO_TENANT_ID,
            party_id=party_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/0101",
            entry_date=date.today() - timedelta(days=10),
        )
        inv2 = LedgerEntry(
            id=inv2_id,
            tenant_id=DEMO_TENANT_ID,
            party_id=party_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("2000.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/0102",
            entry_date=date.today() - timedelta(days=5),
        )
        session.add_all([inv1, inv2])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Record partial payment receipt of ₹1,600 via UPI with OLDEST_FIRST
        rc_res = await ac.post(
            "/api/v1/ledger/receipts",
            headers=headers,
            json={
                "party_id": party_id,
                "payment_mode": "UPI",
                "reference_number": "UPI/260901/123456",
                "total_amount": "1600.00",
                "allocation_method": "OLDEST_FIRST",
                "notes": "Partial payment by contractor",
            },
        )
        assert rc_res.status_code == 201
        rc_data = rc_res.json()

        # Check allocations: Bill 1 fully settled (₹1,000), Bill 2 partially settled (₹600)
        assert Decimal(str(rc_data["total_amount"])) == Decimal("1600.00")
        assert Decimal(str(rc_data["allocated_amount"])) == Decimal("1600.00")
        assert Decimal(str(rc_data["unallocated_amount"])) == Decimal("0.00")
        assert Decimal(str(rc_data["party_current_balance"])) == Decimal("1400.00")
        assert len(rc_data["allocations"]) == 2

        alloc_map = {a["invoice_entry_id"]: Decimal(str(a["allocated_amount"])) for a in rc_data["allocations"]}
        assert alloc_map[inv1_id] == Decimal("1000.00")
        assert alloc_map[inv2_id] == Decimal("600.00")

        # Check open dues: Bill 1 is absent (fully settled), Bill 2 has ₹1,400 remaining due
        dues_res = await ac.get(f"/api/v1/ledger/parties/{party_id}/dues", headers=headers)
        assert dues_res.status_code == 200
        dues = dues_res.json()
        assert len(dues) == 1
        assert dues[0]["entry_id"] == inv2_id
        assert Decimal(str(dues[0]["due_amount"])) == Decimal("1400.00")
        assert Decimal(str(dues[0]["allocated_amount"])) == Decimal("600.00")


@pytest.mark.asyncio
async def test_manual_allocation_and_unallocated_advance():
    """Verify manual invoice allocation and advance retention adhering to exact paisa integrity."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Murugan Plumbers",
                "phone": "9840998877",
            },
        )
        party_id = p_res.json()["id"]

    inv1_id = str(uuid.uuid4())
    inv2_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        party = await session.scalar(select(Party).where(Party.id == party_id))
        party.current_balance = Decimal("2500.00")

        inv1 = LedgerEntry(
            id=inv1_id,
            tenant_id=DEMO_TENANT_ID,
            party_id=party_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/0201",
            entry_date=date.today() - timedelta(days=20),
        )
        inv2 = LedgerEntry(
            id=inv2_id,
            tenant_id=DEMO_TENANT_ID,
            party_id=party_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("1500.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/0202",
            entry_date=date.today() - timedelta(days=5),
        )
        session.add_all([inv1, inv2])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Pay ₹2,000 targeting newer Bill 2 directly for ₹1,500, leaving ₹500 unallocated advance
        rc_res = await ac.post(
            "/api/v1/ledger/receipts",
            headers=headers,
            json={
                "party_id": party_id,
                "payment_mode": "NEFT_RTGS",
                "total_amount": "2000.00",
                "allocation_method": "MANUAL",
                "manual_allocations": [
                    {"invoice_entry_id": inv2_id, "amount": "1500.00"}
                ],
                "notes": "Direct settlement of Bill 2 + Advance",
            },
        )
        assert rc_res.status_code == 201
        data = rc_res.json()

        assert Decimal(str(data["allocated_amount"])) == Decimal("1500.00")
        assert Decimal(str(data["unallocated_amount"])) == Decimal("500.00")
        assert Decimal(str(data["party_current_balance"])) == Decimal("500.00")

        # Verify Ageing Summary and Paisa-level integrity:
        # SUM(Unpaid Invoices) - Unallocated Advances == current_balance
        # Bill 1 is ₹1,000 unpaid; Advance is ₹500; 1000 - 500 == 500
        ageing_res = await ac.get(f"/api/v1/ledger/parties/{party_id}/ageing", headers=headers)
        assert ageing_res.status_code == 200
        ag = ageing_res.json()
        assert Decimal(str(ag["unallocated_advance"])) == Decimal("500.00")
        assert Decimal(str(ag["current_balance"])) == Decimal("500.00")
        assert len(ag["open_invoices"]) == 1
        assert ag["open_invoices"][0]["entry_id"] == inv1_id
        assert Decimal(str(ag["open_invoices"][0]["due_amount"])) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_ageing_buckets_classification():
    """Verify ageing classification into 4 distinct buckets: 0-30, 31-60, 61-90, 90+ days."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Sundaram Hardware Works",
                "phone": "9444112233",
                "credit_days": 15,
            },
        )
        party_id = p_res.json()["id"]

    today = date.today()
    entries = [
        (str(uuid.uuid4()), Decimal("100.00"), today - timedelta(days=10), "INV/B1"),   # 0-30
        (str(uuid.uuid4()), Decimal("200.00"), today - timedelta(days=45), "INV/B2"),   # 31-60
        (str(uuid.uuid4()), Decimal("300.00"), today - timedelta(days=75), "INV/B3"),   # 61-90
        (str(uuid.uuid4()), Decimal("400.00"), today - timedelta(days=120), "INV/B4"),  # 90+
    ]

    async with async_session_factory() as session:
        party = await session.scalar(select(Party).where(Party.id == party_id))
        party.current_balance = Decimal("1000.00")

        for eid, amt, dt, num in entries:
            session.add(
                LedgerEntry(
                    id=eid,
                    tenant_id=DEMO_TENANT_ID,
                    party_id=party_id,
                    entry_type="SALES_INVOICE",
                    debit_amount=amt,
                    credit_amount=Decimal("0.00"),
                    reference_doc_type="SALES_INVOICE",
                    reference_doc_id=str(uuid.uuid4()),
                    reference_doc_number=num,
                    entry_date=dt,
                )
            )
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/ledger/parties/{party_id}/ageing", headers=headers)
        assert res.status_code == 200
        ag = res.json()

        assert Decimal(str(ag["bucket_0_30"])) == Decimal("100.00")
        assert Decimal(str(ag["bucket_31_60"])) == Decimal("200.00")
        assert Decimal(str(ag["bucket_61_90"])) == Decimal("300.00")
        assert Decimal(str(ag["bucket_90_plus"])) == Decimal("400.00")
        assert Decimal(str(ag["current_balance"])) == Decimal("1000.00")

        # Bills B2, B3, B4 are older than credit_days (15), so 200 + 300 + 400 = 900 is overdue
        assert Decimal(str(ag["total_overdue"])) == Decimal("900.00")


@pytest.mark.asyncio
async def test_supplier_balances_and_payments():
    """Verify supplier purchases, payment debit vouchers, and net payables."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create Supplier party
        s_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "SUPPLIER",
                "name": "Tata Steel Tubes Agency",
                "phone": "9884011223",
                "gstin": "33AAACT1234F1Z0",
            },
        )
        assert s_res.status_code == 201
        supplier_id = s_res.json()["id"]

    # Record purchase bill: ₹50,000 credit to supplier (we owe ₹50,000)
    async with async_session_factory() as session:
        supplier = await session.scalar(select(Party).where(Party.id == supplier_id))
        supplier.current_balance = Decimal("-50000.00")

        purchase_entry = LedgerEntry(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            party_id=supplier_id,
            entry_type="PURCHASE_BILL",
            debit_amount=Decimal("0.00"),
            credit_amount=Decimal("50000.00"),
            reference_doc_type="PURCHASE_BILL",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="PUR/26-27/0055",
            entry_date=date.today() - timedelta(days=7),
            notes="Inward bulk pipe bundle",
        )
        session.add(purchase_entry)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Verify supplier summary before payment
        sum1 = await ac.get("/api/v1/ledger/suppliers/summary", headers=headers)
        assert sum1.status_code == 200
        sup_data = next((s for s in sum1.json()["suppliers"] if s["supplier_id"] == supplier_id), None)
        assert sup_data is not None
        assert Decimal(str(sup_data["total_purchases"])) == Decimal("50000.00")
        assert Decimal(str(sup_data["total_paid"])) == Decimal("0.00")
        assert Decimal(str(sup_data["net_payable"])) == Decimal("50000.00")

        # Make payment to supplier of ₹20,000 via NEFT
        pay_res = await ac.post(
            "/api/v1/ledger/supplier-payments",
            headers=headers,
            json={
                "supplier_id": supplier_id,
                "payment_mode": "NEFT_RTGS",
                "reference_number": "UTR89012345678",
                "amount": "20000.00",
                "notes": "Part payment for pipe bundle",
            },
        )
        assert pay_res.status_code == 201
        pay_data = pay_res.json()
        assert Decimal(str(pay_data["amount"])) == Decimal("20000.00")
        assert Decimal(str(pay_data["supplier_current_balance"])) == Decimal("-30000.00")

        # Verify updated supplier summary
        sum2 = await ac.get("/api/v1/ledger/suppliers/summary", headers=headers)
        sup_data2 = next((s for s in sum2.json()["suppliers"] if s["supplier_id"] == supplier_id), None)
        assert sup_data2 is not None
        assert Decimal(str(sup_data2["total_purchases"])) == Decimal("50000.00")
        assert Decimal(str(sup_data2["total_paid"])) == Decimal("20000.00")
        assert Decimal(str(sup_data2["net_payable"])) == Decimal("30000.00")


@pytest.mark.asyncio
async def test_collection_reminders_and_whatsapp_dispatch():
    """Verify prioritized call list ranking and WhatsApp reminder message generation."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create a debtor customer
        p_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Selvam Civil Engineers",
                "phone": "9842154321",
                "credit_days": 10,
            },
        )
        party_id = p_res.json()["id"]

    # Post overdue invoice (25 days old, credit days=10 => 15 days overdue) of ₹12,000
    async with async_session_factory() as session:
        party = await session.scalar(select(Party).where(Party.id == party_id))
        party.current_balance = Decimal("12000.00")

        inv = LedgerEntry(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            party_id=party_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("12000.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/0888",
            entry_date=date.today() - timedelta(days=25),
        )
        session.add(inv)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Fetch Call List
        call_res = await ac.get("/api/v1/ledger/reminders/call-list", headers=headers)
        assert call_res.status_code == 200
        items = call_res.json()
        target = next((item for item in items if item["party_id"] == party_id), None)
        assert target is not None

        assert target["days_overdue"] == 15
        assert Decimal(str(target["overdue_amount"])) == Decimal("12000.00")
        assert Decimal(str(target["urgency_score"])) > Decimal("0.00")

        # Bilingual Tamil message & UPI QR link check
        assert "வணக்கம் Selvam Civil Engineers" in target["whatsapp_message"]
        assert "INV/26-27/0888" in target["whatsapp_message"]
        assert "upi://pay?" in target["upi_payment_link"]

        # 2. Dispatch WhatsApp reminder
        disp_res = await ac.post(
            "/api/v1/ledger/reminders/dispatch-whatsapp",
            headers=headers,
            json={"party_id": party_id},
        )
        assert disp_res.status_code == 200
        disp_data = disp_res.json()
        assert disp_data["party_id"] == party_id
        assert disp_data["recipient_phone"] == "9842154321"
        assert disp_data["status"] == "SENT"

    # Verify log entry in DB
    async with async_session_factory() as session:
        log = await session.scalar(
            select(CollectionReminderLog).where(
                CollectionReminderLog.tenant_id == DEMO_TENANT_ID,
                CollectionReminderLog.party_id == party_id,
            )
        )
        assert log is not None
        assert log.recipient_phone == "9842154321"
        assert "INV/26-27/0888" in log.message_text
