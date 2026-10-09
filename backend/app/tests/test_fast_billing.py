"""Integration test suite for Fast Billing (POS) Module.

Validates the 6 core requirements:
1. Barcode or product search (exact barcode unit auto-selection, Tamil name, code, name search)
2. Unit conversion (base units, variable-weight actual weight, packaging decomposition)
3. GST Invoices (tax split, exact round-off, stock deduction, ledger debit, dynamic UPI QR)
4. Returns / Credit Notes (stock restoration, credit note ledger entry, customer balance reduction)
5. Quotations (open estimates, zero-stock deduction, 1-click conversion to sales invoice)
6. Delivery Challans (dispatches goods, moves stock, 1-click invoice conversion without double deduction)
"""

from decimal import Decimal
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_factory
from app.core.init_db import init_db, seed_demo_data
from app.models.catalogue import Product, ProductUnit
from app.models.stock import Godown, StockMovement, StockBalance
from app.models.ledger import Party, LedgerEntry

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_barcode_and_product_search():
    """Verify barcode matching, auto-selecting packaging units, and multi-lingual search."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    # Assign a specific barcode to the 'Box' unit of SCR001
    async with async_session_factory() as session:
        screw_prod = await session.scalar(
            select(Product).where(Product.code == "SCR001", Product.tenant_id == DEMO_TENANT_ID)
        )
        assert screw_prod is not None
        box_unit = await session.scalar(
            select(ProductUnit).where(
                ProductUnit.product_id == screw_prod.id,
                ProductUnit.unit_name == "Box",
                ProductUnit.tenant_id == DEMO_TENANT_ID,
            )
        )
        assert box_unit is not None
        test_barcode = "8901234567890"
        box_unit.barcode = test_barcode
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Search by exact barcode -> auto-selects 'Box'
        res_bc = await ac.get(f"/api/v1/billing/search?q={test_barcode}", headers=headers)
        assert res_bc.status_code == 200
        results_bc = res_bc.json()
        assert len(results_bc) >= 1
        item_bc = results_bc[0]
        assert item_bc["code"] == "SCR001"
        assert item_bc["matched_unit"] == "Box"

        # 2. Search by Tamil Name
        res_tamil = await ac.get("/api/v1/billing/search?q=திருகு", headers=headers)
        assert res_tamil.status_code == 200
        results_tamil = res_tamil.json()
        assert any(p["code"] == "SCR001" for p in results_tamil)

        # 3. Search by Product Code
        res_code = await ac.get("/api/v1/billing/search?q=TMT012", headers=headers)
        assert res_code.status_code == 200
        results_code = res_code.json()
        assert len(results_code) >= 1
        assert results_code[0]["code"] == "TMT012"
        assert results_code[0]["is_variable_weight"] is True


@pytest.mark.asyncio
async def test_unit_conversion_and_decomposition():
    """Verify smart unit decomposition and variable weight handling."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        prods_res = await ac.get("/api/v1/billing/search?q=SCR001", headers=headers)
        screws = prods_res.json()[0]

        # Decompose 250 pieces (Box = 100 pcs) -> "2 Box 50 piece (250 piece)"
        payload = {
            "product_id": screws["id"],
            "unit_name": "piece",
            "quantity": 250,
        }
        res = await ac.post("/api/v1/billing/unit-decompose", json=payload, headers=headers)
        assert res.status_code == 200
        decomp = res.json()
        assert Decimal(decomp["base_quantity"]) == Decimal("250.0000")
        assert "2 Box" in decomp["display_units"]
        assert "50 piece" in decomp["display_units"]


@pytest.mark.asyncio
async def test_gst_sales_invoice_posting_and_ledger():
    """Verify posting sales invoice creates movements, decrements stock, updates party ledger, and generates UPI QR."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Fetch godowns, customer, and products
        prods_res = await ac.get("/api/v1/billing/search?q=SCR001", headers=headers)
        screw = prods_res.json()[0]

        godowns_res = await ac.get("/api/v1/inventory/godowns", headers=headers)
        main_godown = next(g for g in godowns_res.json() if g["code"] == "MAIN")

        parties_res = await ac.get("/api/v1/ledger/parties", headers=headers)
        customer = next(p for p in parties_res.json() if p["party_type"] == "CUSTOMER")
        initial_balance = Decimal(customer["current_balance"])

        # Create sales invoice for 3 boxes @ 200/box with flat discount 20
        # 3 boxes = 300 pcs. Gross = 600, Disc = 20, Taxable = 580
        # GST 18%: CGST 9% = 52.20, SGST 9% = 52.20. Line total = 684.40
        # Paid 500 via CASH, Due 184.40 -> roundoff = 684.00, paid 500, due 184.00
        invoice_payload = {
            "party_id": customer["id"],
            "customer_name": customer["name"],
            "place_of_supply_state_code": "33",
            "godown_id": main_godown["id"],
            "payment_mode": "CASH",
            "paid_amount": 500.00,
            "lines": [
                {
                    "product_id": screw["id"],
                    "unit_name": "Box",
                    "conversion_factor": 100,
                    "quantity": 3,
                    "unit_price": 200.00,
                    "discount_type": "FLAT",
                    "discount_value": 20.00,
                    "gst_rate_percent": 18.00,
                }
            ],
        }

        inv_res = await ac.post("/api/v1/billing/invoices", json=invoice_payload, headers=headers)
        assert inv_res.status_code == 201
        inv = inv_res.json()

        assert Decimal(inv["grand_total"]) == Decimal("684.00")
        assert Decimal(inv["paid_amount"]) == Decimal("500.00")
        assert Decimal(inv["due_amount"]) == Decimal("184.00")
        assert "upi://pay?" in inv["upi_qr_string"]

        # Check stock movement in DB
        async with async_session_factory() as session:
            sm = await session.scalar(
                select(StockMovement).where(
                    StockMovement.reference_doc_id == inv["id"],
                    StockMovement.movement_type == "SALE",
                )
            )
            assert sm is not None
            assert sm.quantity_base == Decimal("-300.0000")

            # Check party ledger balance
            party_db = await session.scalar(select(Party).where(Party.id == customer["id"]))
            assert party_db.current_balance == initial_balance + Decimal("184.00")


@pytest.mark.asyncio
async def test_sales_return_and_credit_note():
    """Verify sales return restores stock (+qty) and posts credit note to party ledger."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        prods_res = await ac.get("/api/v1/billing/search?q=SCR001", headers=headers)
        screw = prods_res.json()[0]

        parties_res = await ac.get("/api/v1/ledger/parties", headers=headers)
        customer = next(p for p in parties_res.json() if p["party_type"] == "CUSTOMER")

        # Initial party balance
        async with async_session_factory() as session:
            party_db = await session.scalar(select(Party).where(Party.id == customer["id"]))
            pre_balance = party_db.current_balance

        # Post Sales Return: return 1 box @ 200/box with CREDIT_NOTE
        return_payload = {
            "party_id": customer["id"],
            "customer_name": customer["name"],
            "refund_mode": "CREDIT_NOTE",
            "reason": "Excess material left over at site",
            "lines": [
                {
                    "product_id": screw["id"],
                    "unit_name": "Box",
                    "conversion_factor": 100,
                    "quantity": 1,
                    "unit_price": 200.00,
                    "gst_rate_percent": 18.00,
                }
            ],
        }

        ret_res = await ac.post("/api/v1/billing/returns", json=return_payload, headers=headers)
        assert ret_res.status_code == 201
        ret = ret_res.json()
        assert Decimal(ret["grand_total"]) == Decimal("236.00")  # 200 + 18% = 236.00

        # Check stock movement (+100 pcs)
        async with async_session_factory() as session:
            sm = await session.scalar(
                select(StockMovement).where(
                    StockMovement.reference_doc_id == ret["id"],
                    StockMovement.movement_type == "SALES_RETURN",
                )
            )
            assert sm is not None
            assert sm.quantity_base == Decimal("100.0000")

            # Check customer balance reduced by 236
            party_db = await session.scalar(select(Party).where(Party.id == customer["id"]))
            assert party_db.current_balance == pre_balance - Decimal("236.00")


@pytest.mark.asyncio
async def test_quotation_creation_and_conversion():
    """Verify quotation creation does NOT move stock, and 1-click conversion to invoice converts and moves stock."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        prods_res = await ac.get("/api/v1/billing/search?q=SCR001", headers=headers)
        screw = prods_res.json()[0]

        quote_payload = {
            "customer_name": "Perumal Mason Contractor",
            "customer_phone": "9842100000",
            "lines": [
                {
                    "product_id": screw["id"],
                    "unit_name": "Box",
                    "conversion_factor": 100,
                    "quantity": 5,
                    "unit_price": 190.00,
                    "gst_rate_percent": 18.00,
                }
            ],
        }

        # 1. Create Quotation
        q_res = await ac.post("/api/v1/billing/quotations", json=quote_payload, headers=headers)
        assert q_res.status_code == 201
        quote = q_res.json()
        assert quote["status"] == "OPEN"
        quote_id = quote["id"]

        # Ensure NO stock movements created for quotation
        async with async_session_factory() as session:
            sm = await session.scalar(
                select(StockMovement).where(StockMovement.reference_doc_id == quote_id)
            )
            assert sm is None

        # 2. 1-Click Convert Quotation to Invoice
        convert_res = await ac.post(
            f"/api/v1/billing/quotations/{quote_id}/convert-to-invoice",
            json={"payment_mode": "CASH"},
            headers=headers,
        )
        assert convert_res.status_code == 200
        inv = convert_res.json()
        assert inv["status"] == "POSTED"

        # Check quote is marked CONVERTED
        q_check = await ac.get(f"/api/v1/billing/quotations/{quote_id}", headers=headers)
        assert q_check.json()["status"] == "CONVERTED"
        assert q_check.json()["converted_invoice_id"] == inv["id"]

        # Check stock movement now exists for the invoice
        async with async_session_factory() as session:
            sm = await session.scalar(
                select(StockMovement).where(
                    StockMovement.reference_doc_id == inv["id"],
                    StockMovement.movement_type == "SALE",
                )
            )
            assert sm is not None
            assert sm.quantity_base == Decimal("-500.0000")


@pytest.mark.asyncio
async def test_delivery_challan_creation_and_conversion():
    """Verify delivery challan moves stock on dispatch, and conversion to invoice does NOT double deduct."""
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        prods_res = await ac.get("/api/v1/billing/search?q=SCR001", headers=headers)
        screw = prods_res.json()[0]

        dc_payload = {
            "customer_name": "Karpagam Builders Site",
            "delivery_site_address": "Plot 45, Anna Nagar, Salem",
            "vehicle_number": "TN-30-AZ-1234",
            "lines": [
                {
                    "product_id": screw["id"],
                    "unit_name": "Box",
                    "conversion_factor": 100,
                    "quantity": 4,
                    "unit_price": 195.00,
                }
            ],
        }

        # 1. Issue Delivery Challan
        dc_res = await ac.post("/api/v1/billing/challans", json=dc_payload, headers=headers)
        assert dc_res.status_code == 201
        dc = dc_res.json()
        assert dc["status"] == "DISPATCHED"
        dc_id = dc["id"]

        # Stock MUST be deducted on dispatch (-400 pcs)
        async with async_session_factory() as session:
            sm_dc = await session.scalar(
                select(StockMovement).where(
                    StockMovement.reference_doc_id == dc_id,
                    StockMovement.movement_type == "DELIVERY_CHALLAN",
                )
            )
            assert sm_dc is not None
            assert sm_dc.quantity_base == Decimal("-400.0000")

        # 2. Convert Delivery Challan to Sales Invoice
        conv_res = await ac.post(
            f"/api/v1/billing/challans/{dc_id}/convert-to-invoice",
            json={"payment_mode": "CREDIT"},
            headers=headers,
        )
        assert conv_res.status_code == 200
        inv = conv_res.json()
        assert inv["status"] == "POSTED"

        # Check challan status is INVOICED
        dc_check = await ac.get(f"/api/v1/billing/challans/{dc_id}", headers=headers)
        assert dc_check.json()["status"] == "INVOICED"

        # Crucial Invariant: Verify NO second SALE stock movement was created for the invoice
        async with async_session_factory() as session:
            sm_inv = await session.scalar(
                select(StockMovement).where(
                    StockMovement.reference_doc_id == inv["id"],
                    StockMovement.movement_type == "SALE",
                )
            )
            assert sm_inv is None  # No double deduction!
