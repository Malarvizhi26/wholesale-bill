"""Integration tests for Module 5: AI Business Assistant.

Validates the authoritative specifications of AGENTS.md:
1. Strict Architecture: LLM never writes SQL and never performs raw arithmetic.
2. Fixed tool calling for:
   - profit_by_product
   - get_receivables
   - reorder_suggestions
   - sales_summary
   - dead_stock
   - customer_summary
   - payables_due
3. Dual language response output (Tamil & English) with tabular cards and direct links.
"""

from datetime import date, datetime, timedelta, timezone
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
from app.models.stock import Godown, StockBalance, StockMovement
from app.models.ledger import Party, LedgerEntry
from app.models.billing import SalesInvoice, SalesInvoiceLine
from app.modules.ai_assistant.ai_service import AIAssistantService

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def _default_price_list_id(session) -> str:
    """Real FK target (SQLite does not enforce foreign keys, PostgreSQL does)."""
    from app.models.catalogue import PriceList
    return await session.scalar(select(PriceList.id).where(PriceList.tenant_id == DEMO_TENANT_ID, PriceList.is_default.is_(True)))


async def _primary_godown_id(session) -> str:
    from app.models.stock import Godown
    return await session.scalar(select(Godown.id).where(Godown.tenant_id == DEMO_TENANT_ID, Godown.is_primary.is_(True)))


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_ai_profit_by_product_query():
    """Verify query 'Which products made the most profit this month?' calls profit_by_product."""
    async with async_session_factory() as session:
        # Get demo products
        prods = (await session.execute(select(Product).where(Product.tenant_id == DEMO_TENANT_ID))).scalars().all()
        p1 = prods[0]

        # Post an invoice with profit
        inv_id = str(uuid.uuid4())
        inv = SalesInvoice(
            id=inv_id,
            tenant_id=DEMO_TENANT_ID,
            invoice_number=f"INV/26-27/AI_{uuid.uuid4().hex[:6]}",
            invoice_date=datetime.now(timezone.utc),
            customer_name="Cash Walk-in",
            place_of_supply_state_code="33",
            price_list_id=await _default_price_list_id(session),
            godown_id=await _primary_godown_id(session),
            status="POSTED",
            subtotal_amount=Decimal("5000.00"),
            discount_amount=Decimal("0.00"),
            cgst_amount=Decimal("450.00"),
            sgst_amount=Decimal("450.00"),
            igst_amount=Decimal("0.00"),
            total_tax_amount=Decimal("900.00"),
            round_off_amount=Decimal("0.00"),
            grand_total=Decimal("5900.00"),
            paid_amount=Decimal("5900.00"),
            payment_mode="CASH",
        )
        session.add(inv)

        line = SalesInvoiceLine(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            invoice_id=inv_id,
            line_number=1,
            product_id=p1.id,
            unit_name=p1.base_unit,
            conversion_factor=Decimal("1.0000"),
            quantity=Decimal("10.0000"),
            base_quantity=Decimal("10.0000"),
            unit_price=Decimal("500.00"),
            cost_price_base_at_sale=Decimal("350.0000"),  # Cost = 3500, Taxable = 5000, Profit = 1500
            discount_type="FLAT",
            discount_value=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            taxable_amount=Decimal("5000.00"),
            hsn_code=p1.hsn_code or "7214",
            gst_rate_percent=Decimal("18.00"),
            cgst_percent=Decimal("9.00"),
            cgst_amount=Decimal("450.00"),
            sgst_percent=Decimal("9.00"),
            sgst_amount=Decimal("450.00"),
            igst_percent=Decimal("0.00"),
            igst_amount=Decimal("0.00"),
            line_total=Decimal("5900.00"),
        )
        session.add(line)
        await session.commit()

        # Execute query through AIAssistantService
        res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Which products made the most profit this month?",
        )

        assert res.tool_called == "profit_by_product"
        assert res.detected_intent == "profit_by_product"
        assert "₹" in res.answer_en
        assert "லாபம்" in res.answer_ta
        assert res.data_card is not None
        assert len(res.data_card.rows) > 0
        assert res.action_link is not None
        assert res.action_link.route == "/reports?tab=margin"


@pytest.mark.asyncio
async def test_ai_get_receivables_query():
    """Verify query 'Who owes me money?' calls get_receivables and outputs credit dues."""
    async with async_session_factory() as session:
        # Create a debtor customer
        cust_id = str(uuid.uuid4())
        cust = Party(
            id=cust_id,
            tenant_id=DEMO_TENANT_ID,
            name="Suresh Civil Works",
            party_type="CUSTOMER",
            phone="9876543210",
            credit_limit=Decimal("50000.00"),
            credit_days=30,
            current_balance=Decimal("14500.00"),
            is_active=True,
        )
        session.add(cust)
        await session.flush()  # no relationship(): insert the party before its ledger entry

        # Add overdue debit ledger entry (45 days old)
        entry_date = date.today() - timedelta(days=45)
        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            party_id=cust_id,
            entry_type="SALES_INVOICE",
            debit_amount=Decimal("14500.00"),
            credit_amount=Decimal("0.00"),
            reference_doc_type="SALES_INVOICE",
            reference_doc_id=str(uuid.uuid4()),
            reference_doc_number="INV/26-27/DEBT_01",
            entry_date=entry_date,
            notes="Credit sale for TMT steel rods",
        )
        session.add(entry)
        await session.commit()

        res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Who owes me money?",
        )

        assert res.tool_called == "get_receivables"
        assert res.detected_intent == "get_receivables"
        assert "14,500.00" in res.answer_en or "₹" in res.answer_en
        assert "கடன் பாக்கி" in res.answer_ta
        assert res.data_card is not None
        assert any(r["party_name"] == "Suresh Civil Works" for r in res.data_card.rows)
        assert res.action_link is not None
        assert res.action_link.route == "/ledger"


@pytest.mark.asyncio
async def test_ai_reorder_suggestions_query():
    """Verify query 'Which items should I reorder?' calls reorder_suggestions."""
    async with async_session_factory() as session:
        # Create product with low stock
        godown = (await session.execute(select(Godown).where(Godown.tenant_id == DEMO_TENANT_ID))).scalars().first()
        prod_id = str(uuid.uuid4())
        low_prod = Product(
            id=prod_id,
            tenant_id=DEMO_TENANT_ID,
            code=f"LOW_BOLT_{uuid.uuid4().hex[:6]}",
            name="M10 Hex Bolt 50mm",
            tamil_name="M10 திருகாணி",
            hsn_code="7318",
            base_unit="PCS",
            purchase_price_base=Decimal("5.00"),
            min_stock_base=Decimal("100.0000"),
            reorder_quantity_base=Decimal("200.0000"),
            is_active=True,
        )
        session.add(low_prod)

        # Set stock balance to 15 PCS (deficit = 85 PCS)
        bal = StockBalance(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            godown_id=godown.id,
            product_id=prod_id,
            current_quantity_base=Decimal("15.0000"),
            weighted_avg_cost_base=Decimal("5.00"),
        )
        session.add(bal)
        await session.commit()

        res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Which items should I reorder?",
        )

        assert res.tool_called == "reorder_suggestions"
        assert res.detected_intent == "reorder_suggestions"
        assert "below minimum stock" in res.answer_en or "items" in res.answer_en
        assert "குறைந்தபட்ச இருப்பு" in res.answer_ta or "ஆர்டர்" in res.answer_ta
        assert res.data_card is not None
        assert res.action_link is not None
        assert res.action_link.route == "/inventory?tab=alerts"


@pytest.mark.asyncio
async def test_ai_sales_summary_and_dead_stock():
    """Verify sales summary and dead stock queries."""
    async with async_session_factory() as session:
        # 1. Sales summary query
        sales_res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="How much did I sell today?",
        )
        assert sales_res.tool_called == "sales_summary"
        assert "Total sales" in sales_res.answer_en
        assert "விற்பனை" in sales_res.answer_ta
        assert sales_res.action_link.route == "/reports?tab=daily"

        # 2. Dead stock query
        dead_res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Which items are dead stock for 60 days?",
        )
        assert dead_res.tool_called == "dead_stock"
        assert "dead stock" in dead_res.answer_en or "No dead stock" in dead_res.answer_en
        assert "தேக்கமடைந்த" in dead_res.answer_ta or "தேக்க" in dead_res.answer_ta
        assert dead_res.action_link.route == "/reports?tab=valuation"


@pytest.mark.asyncio
async def test_ai_customer_and_supplier_queries():
    """Verify specific customer lookup and supplier payables."""
    async with async_session_factory() as session:
        # Supplier check
        supp_res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Whom do I owe money to?",
        )
        assert supp_res.tool_called == "payables_due"
        assert "supplier" in supp_res.answer_en.lower()
        assert "சப்ளையர்" in supp_res.answer_ta
        assert supp_res.action_link.route == "/ledger?tab=suppliers"

        # Customer summary query
        cust_res = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="Customer summary for Suresh",
        )
        assert cust_res.tool_called == "customer_summary"
        assert "Suresh" in cust_res.answer_en or "customer" in cust_res.answer_en.lower()


@pytest.mark.asyncio
async def test_ai_tamil_natural_language_queries():
    """Verify native Tamil phrasing executes correct domain tools."""
    async with async_session_factory() as session:
        # 1. யாருக்கு கடன் பாக்கி உள்ளது? -> get_receivables
        t1 = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="யாருக்கு கடன் பாக்கி உள்ளது?",
        )
        assert t1.tool_called == "get_receivables"
        assert "கடன் பாக்கி" in t1.answer_ta

        # 2. இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை? -> profit_by_product
        t2 = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?",
        )
        assert t2.tool_called == "profit_by_product"
        assert "லாபம்" in t2.answer_ta

        # 3. எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்? -> reorder_suggestions
        t3 = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?",
        )
        assert t3.tool_called == "reorder_suggestions"

        # 4. இன்றைய விற்பனை எவ்வளவு? -> sales_summary
        t4 = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="இன்றைய விற்பனை எவ்வளவு?",
        )
        assert t4.tool_called == "sales_summary"

        # 5. சப்ளையர் பாக்கி எவ்வளவு? -> payables_due
        t5 = await AIAssistantService.process_query(
            session=session,
            tenant_id=DEMO_TENANT_ID,
            query="சப்ளையர் பாக்கி எவ்வளவு?",
        )
        assert t5.tool_called == "payables_due"


@pytest.mark.asyncio
async def test_ai_http_api_endpoints():
    """Verify POST /api/v1/ai/query and GET /api/v1/ai/suggestions endpoints."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Suggestions endpoint
        sug_res = await client.get("/api/v1/ai/suggestions", headers=headers)
        assert sug_res.status_code == 200
        suggestions = sug_res.json()
        assert len(suggestions) >= 6
        assert any("profit" in s["query"].lower() for s in suggestions)
        assert any("owes" in s["query"].lower() for s in suggestions)
        assert any("reorder" in s["query"].lower() for s in suggestions)

        # 2. Query endpoint: profit question
        q1_res = await client.post(
            "/api/v1/ai/query",
            json={"query": "Which products made the most profit this month?"},
            headers=headers,
        )
        assert q1_res.status_code == 200
        data1 = q1_res.json()
        assert data1["tool_called"] == "profit_by_product"
        assert data1["answer_en"] != ""
        assert data1["answer_ta"] != ""
        assert data1["data_card"] is not None

        # 3. Query endpoint: who owes me money
        q2_res = await client.post(
            "/api/v1/ai/query",
            json={"query": "Who owes me money?"},
            headers=headers,
        )
        assert q2_res.status_code == 200
        data2 = q2_res.json()
        assert data2["tool_called"] == "get_receivables"
        assert data2["action_link"]["route"] == "/ledger"

        # 4. Query endpoint: reorder
        q3_res = await client.post(
            "/api/v1/ai/query",
            json={"query": "Which items should I reorder?"},
            headers=headers,
        )
        assert q3_res.status_code == 200
        data3 = q3_res.json()
        assert data3["tool_called"] == "reorder_suggestions"
        assert data3["action_link"]["route"] == "/inventory?tab=alerts"
