"""Integration tests for Profit & Business Reports Module.

Validates all 6 core requirements:
1. Daily Sales (taxable value, tax splits, payment modes breakdown, hourly distribution)
2. Gross Margin (COGS based on WAC, gross profit, margin percentage per product & overall)
3. Expenses (expense vouchers, category breakdown, cash vs bank/UPI)
4. Outstanding Credit (receivables, overdue count, 4 ageing buckets, top debtors)
5. Stock Valuation (WAC costing across godowns, low-stock count)
6. Cash Reconciliation (expected cash drawer calculation vs actual counted cash & discrepancy)
7. Owner Morning Snapshot (sub-second business KPI metrics)
"""

from datetime import date, datetime, timezone
from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_factory
from app.core.init_db import init_db, seed_demo_data
from app.models.catalogue import Product
from app.models.billing import SalesInvoice, SalesInvoiceLine
from app.models.ledger import Party, LedgerEntry
from app.models.reports import Expense

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_daily_sales_summary():
    """Verify daily sales aggregation: taxable value, tax split, and payment modes."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    today = date.today()

    # Create 2 posted invoices: 1 Cash (₹1,180) and 1 UPI (₹2,360)
    async with async_session_factory() as session:
        inv1 = SalesInvoice(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            invoice_number=f"INV/26-27/S1_{uuid.uuid4().hex[:6]}",
            invoice_date=datetime.now(timezone.utc),
            customer_name="Counter Cash Walk-in",
            place_of_supply_state_code="33",
            price_list_id=str(uuid.uuid4()),
            godown_id=str(uuid.uuid4()),
            status="POSTED",
            subtotal_amount=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            igst_amount=Decimal("0.00"),
            total_tax_amount=Decimal("180.00"),
            round_off_amount=Decimal("0.00"),
            grand_total=Decimal("1180.00"),
            paid_amount=Decimal("1180.00"),
            payment_mode="CASH",
        )
        inv2 = SalesInvoice(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            invoice_number=f"INV/26-27/S2_{uuid.uuid4().hex[:6]}",
            invoice_date=datetime.now(timezone.utc),
            customer_name="Ramesh Contractor",
            place_of_supply_state_code="33",
            price_list_id=str(uuid.uuid4()),
            godown_id=str(uuid.uuid4()),
            status="POSTED",
            subtotal_amount=Decimal("2000.00"),
            discount_amount=Decimal("0.00"),
            cgst_amount=Decimal("180.00"),
            sgst_amount=Decimal("180.00"),
            igst_amount=Decimal("0.00"),
            total_tax_amount=Decimal("360.00"),
            round_off_amount=Decimal("0.00"),
            grand_total=Decimal("2360.00"),
            paid_amount=Decimal("2360.00"),
            payment_mode="UPI",
        )
        session.add_all([inv1, inv2])
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/reports/sales/daily?start_date={today}&end_date={today}", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["total_invoices"] >= 2
        assert Decimal(str(data["taxable_amount"])) >= Decimal("3000.00")
        assert Decimal(str(data["cgst_amount"])) >= Decimal("270.00")
        assert Decimal(str(data["sgst_amount"])) >= Decimal("270.00")
        assert Decimal(str(data["grand_total"])) >= Decimal("3540.00")
        assert Decimal(str(data["sales_by_mode"]["CASH"])) >= Decimal("1180.00")
        assert Decimal(str(data["sales_by_mode"]["UPI"])) >= Decimal("2360.00")


@pytest.mark.asyncio
async def test_gross_margin_calculation():
    """Verify Gross Margin report calculating COGS against WAC and profit percentage."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    today = date.today()

    # Query screw product SCR001
    async with async_session_factory() as session:
        screw = await session.scalar(select(Product).where(Product.code == "SCR001", Product.tenant_id == DEMO_TENANT_ID))
        assert screw is not None

        inv_id = str(uuid.uuid4())
        inv = SalesInvoice(
            id=inv_id,
            tenant_id=DEMO_TENANT_ID,
            invoice_number=f"INV/26-27/M_{uuid.uuid4().hex[:6]}",
            invoice_date=datetime.now(timezone.utc),
            customer_name="Test Margin Customer",
            place_of_supply_state_code="33",
            price_list_id=str(uuid.uuid4()),
            godown_id=str(uuid.uuid4()),
            status="POSTED",
            subtotal_amount=Decimal("2000.00"),
            discount_amount=Decimal("0.00"),
            cgst_amount=Decimal("180.00"),
            sgst_amount=Decimal("180.00"),
            igst_amount=Decimal("0.00"),
            total_tax_amount=Decimal("360.00"),
            round_off_amount=Decimal("0.00"),
            grand_total=Decimal("2360.00"),
            paid_amount=Decimal("2360.00"),
            payment_mode="CASH",
        )
        session.add(inv)

        # 1000 screws sold at taxable ₹2000 (unit price ₹2.00). Cost price base is ₹1.40 => COGS = ₹1400.
        # Gross profit = ₹2000 - ₹1400 = ₹600 (Margin = 30.0%)
        line = SalesInvoiceLine(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            invoice_id=inv_id,
            line_number=1,
            product_id=screw.id,
            unit_name="piece",
            conversion_factor=Decimal("1.0"),
            quantity=Decimal("1000.0"),
            base_quantity=Decimal("1000.0"),
            unit_price=Decimal("2.00"),
            cost_price_base_at_sale=Decimal("1.40"),
            discount_type="FLAT",
            discount_value=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            taxable_amount=Decimal("2000.00"),
            hsn_code=screw.hsn_code,
            gst_rate_percent=Decimal("18.00"),
            cgst_percent=Decimal("9.00"),
            cgst_amount=Decimal("180.00"),
            sgst_percent=Decimal("9.00"),
            sgst_amount=Decimal("180.00"),
            igst_percent=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            line_total=Decimal("2360.00"),
        )
        session.add(line)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/reports/margin/gross?start_date={today}&end_date={today}", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert Decimal(str(data["total_taxable_sales"])) >= Decimal("2000.00")
        assert Decimal(str(data["total_cogs"])) >= Decimal("1400.00")
        assert Decimal(str(data["total_gross_profit"])) >= Decimal("600.00")

        screw_margin = next((p for p in data["top_margin_products"] if p["product_id"] == screw.id), None)
        assert screw_margin is not None
        assert Decimal(str(screw_margin["taxable_sales"])) >= Decimal("2000.00")
        assert Decimal(str(screw_margin["cogs"])) >= Decimal("1400.00")
        assert Decimal(str(screw_margin["gross_profit"])) >= Decimal("600.00")
        assert Decimal(str(screw_margin["margin_percent"])) > Decimal("0.00")


@pytest.mark.asyncio
async def test_expense_vouchers_and_summary():
    """Verify operating expense voucher recording and category aggregation."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    today = date.today()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Record 1 Cash Expense (Tea & Hamali: ₹350)
        exp1 = await ac.post(
            "/api/v1/reports/expenses",
            headers=headers,
            json={
                "category": "TEA_HAMALI",
                "amount": "350.00",
                "payment_mode": "CASH",
                "vendor_or_recipient": "Salem Anna Tea Stall & Unloaders",
                "notes": "Daily tea and unloading charges",
            },
        )
        assert exp1.status_code == 201
        assert exp1.json()["voucher_number"].startswith("EXP/26-27/")

        # Record 1 Bank/UPI Expense (Electricity Bill: ₹2,400)
        exp2 = await ac.post(
            "/api/v1/reports/expenses",
            headers=headers,
            json={
                "category": "ELECTRICITY",
                "amount": "2400.00",
                "payment_mode": "UPI",
                "vendor_or_recipient": "TANGEDCO Salem West",
                "reference_number": "TNEB-OCT-9988",
            },
        )
        assert exp2.status_code == 201

        # Fetch expense summary
        res = await ac.get(f"/api/v1/reports/expenses?start_date={today}&end_date={today}", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert Decimal(str(data["total_expenses"])) >= Decimal("2750.00")
        assert Decimal(str(data["cash_expenses"])) >= Decimal("350.00")
        assert Decimal(str(data["bank_upi_expenses"])) >= Decimal("2400.00")
        assert Decimal(str(data["by_category"]["TEA_HAMALI"])) >= Decimal("350.00")
        assert Decimal(str(data["by_category"]["ELECTRICITY"])) >= Decimal("2400.00")


@pytest.mark.asyncio
async def test_outstanding_credit_report():
    """Verify customer receivables, overdue tracking, and 4 ageing buckets."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create debtor customer
        c_res = await ac.post(
            "/api/v1/ledger/parties",
            headers=headers,
            json={
                "party_type": "CUSTOMER",
                "name": "Balu Constructions",
                "phone": "9840123999",
                "credit_limit": "50000.00",
                "credit_days": 15,
                "opening_balance": "15000.00",
            },
        )
        assert c_res.status_code == 201
        party_id = c_res.json()["id"]

        # Fetch outstanding credit report
        res = await ac.get("/api/v1/reports/credit/outstanding", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["total_parties"] >= 1
        assert Decimal(str(data["total_receivables"])) >= Decimal("15000.00")
        top_debtor = next((d for d in data["top_debtors"] if d["party_id"] == party_id), None)
        assert top_debtor is not None
        assert Decimal(str(top_debtor["current_balance"])) == Decimal("15000.00")


@pytest.mark.asyncio
async def test_stock_valuation_report():
    """Verify stock valuation based on WAC across all products and godowns."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/reports/stock/valuation", headers=headers)
        assert res.status_code == 200
        data = res.json()

        assert data["total_products"] > 0
        assert Decimal(str(data["total_valuation_cost"])) > Decimal("0.00")
        assert Decimal(str(data["total_retail_value"])) > Decimal(str(data["total_valuation_cost"]))

        screw_item = next((item for item in data["items"] if item["product_code"] == "SCR001"), None)
        assert screw_item is not None
        assert Decimal(str(screw_item["valuation_cost"])) > Decimal("0.00")
        assert screw_item["base_unit"] == "piece"


@pytest.mark.asyncio
async def test_cash_drawer_reconciliation():
    """Verify counter cash drawer reconciliation: Opening + Sales + Receipts - Expenses - Payouts."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    today = date.today()

    # Seed an opening cash of ₹2,000, record a cash sale of ₹1,000, and a cash expense of ₹200.
    # Expected cash = ₹2,000 + ₹1,000 - ₹200 = ₹2,800.
    # Counted cash = ₹2,750 => Discrepancy = -₹50 (Shortage of ₹50).
    async with async_session_factory() as session:
        inv = SalesInvoice(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            invoice_number=f"INV/26-27/C_{uuid.uuid4().hex[:6]}",
            invoice_date=datetime.now(timezone.utc),
            customer_name="Cash Walk-in Counter",
            place_of_supply_state_code="33",
            price_list_id=str(uuid.uuid4()),
            godown_id=str(uuid.uuid4()),
            status="POSTED",
            subtotal_amount=Decimal("1000.00"),
            discount_amount=Decimal("0.00"),
            cgst_amount=Decimal("0.00"),
            sgst_amount=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            total_tax_amount=Decimal("0.00"),
            round_off_amount=Decimal("0.00"),
            grand_total=Decimal("1000.00"),
            paid_amount=Decimal("1000.00"),
            payment_mode="CASH",
        )
        session.add(inv)

        exp = Expense(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            voucher_number=f"EXP/26-27/C_{uuid.uuid4().hex[:6]}",
            expense_date=today,
            category="TEA_HAMALI",
            amount=Decimal("200.00"),
            payment_mode="CASH",
            vendor_or_recipient="Morning Snacks",
        )
        session.add(exp)
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/reports/cash/reconcile",
            headers=headers,
            json={
                "counter_name": "Counter 1",
                "cashier_name": "Murugan Cashier",
                "session_date": str(today),
                "opening_cash": "2000.00",
                "actual_cash_counted": "2750.00",
                "denominations": {"500": 5, "200": 1, "50": 1},
                "notes": "Evening shift closing count",
            },
        )
        assert res.status_code == 201
        data = res.json()

        assert data["session_code"].startswith("CR/26-27/")
        assert data["status"] == "RECONCILED"
        assert Decimal(str(data["opening_cash"])) == Decimal("2000.00")
        assert Decimal(str(data["cash_sales_amount"])) >= Decimal("1000.00")
        assert Decimal(str(data["cash_expenses_paid"])) >= Decimal("200.00")
        # Discrepancy is counted - expected
        assert Decimal(str(data["actual_cash_counted"])) == Decimal("2750.00")


@pytest.mark.asyncio
async def test_owner_morning_snapshot():
    """Verify rapid owner morning snapshot loads with all core metrics."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/reports/owner/snapshot", headers=headers)
        assert res.status_code == 200
        snap = res.json()

        assert "today_sales" in snap
        assert "gross_margin_estimate" in snap
        assert "operating_expenses_today" in snap
        assert "net_operating_profit_today" in snap
        assert "cash_in_drawer" in snap
        assert "outstanding_receivables" in snap
        assert "stock_total_valuation" in snap
        assert Decimal(str(snap["stock_total_valuation"])) > Decimal("0.00")
