"""Integration tests for Smart Inventory: Purchases, Adjustments, Godowns, Alerts, and Price History."""

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

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_godowns_listing_creation_and_transfer():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. List Godowns
        res = await ac.get("/api/v1/inventory/godowns", headers=headers)
        assert res.status_code == 200
        godowns = res.json()
        assert len(godowns) >= 2
        main_godown = next(g for g in godowns if g["code"] == "MAIN")
        bypass_godown = next(g for g in godowns if g["code"] == "BYPASS")
        assert main_godown["is_primary"] is True

        # 2. Create Godown
        test_code = f"YARD-{uuid.uuid4().hex[:6].upper()}"
        new_godown_payload = {
            "code": test_code,
            "name": "Steel Storage Yard",
            "is_primary": False,
        }
        res_create = await ac.post("/api/v1/inventory/godowns", json=new_godown_payload, headers=headers)
        assert res_create.status_code == 201
        yard_godown = res_create.json()
        assert yard_godown["code"] == test_code

        # 3. Fetch products to get screw product
        prods_res = await ac.get("/api/v1/inventory/products", headers=headers)
        screws = next(p for p in prods_res.json() if p["code"] == "SCR001")

        # Initial BYPASS stock
        pre_stock_res = await ac.get(f"/api/v1/inventory/godowns/{bypass_godown['id']}/stock", headers=headers)
        pre_screw_stock = next((item for item in pre_stock_res.json() if item["product_id"] == screws["id"]), None)
        pre_qty = Decimal(pre_screw_stock["current_quantity_base"]) if pre_screw_stock else Decimal("0.0000")

        # 4. Transfer 2 Boxes (200 pcs) from MAIN to BYPASS
        transfer_payload = {
            "source_godown_id": main_godown["id"],
            "target_godown_id": bypass_godown["id"],
            "product_id": screws["id"],
            "unit_name": "Box",
            "quantity": 2,
            "conversion_factor": 100,
            "notes": "Truck transfer to bypass warehouse",
        }
        res_trf = await ac.post("/api/v1/inventory/godowns/transfer", json=transfer_payload, headers=headers)
        assert res_trf.status_code == 200
        trf_data = res_trf.json()
        assert trf_data["source_godown_name"] == main_godown["name"]
        assert trf_data["target_godown_name"] == bypass_godown["name"]
        assert trf_data["base_quantity"] == "200.0000"

        # 5. Check BYPASS stock
        res_stock = await ac.get(f"/api/v1/inventory/godowns/{bypass_godown['id']}/stock", headers=headers)
        assert res_stock.status_code == 200
        stock_items = res_stock.json()
        screw_stock = next((item for item in stock_items if item["product_id"] == screws["id"]), None)
        assert screw_stock is not None
        assert Decimal(screw_stock["current_quantity_base"]) == pre_qty + Decimal("200.0000")


@pytest.mark.asyncio
async def test_purchase_bill_landed_cost_and_wac_absorption():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Get godowns and products
        godowns = (await ac.get("/api/v1/inventory/godowns", headers=headers)).json()
        main_godown = next(g for g in godowns if g["code"] == "MAIN")

        products = (await ac.get("/api/v1/inventory/products", headers=headers)).json()
        screws = next(p for p in products if p["code"] == "SCR001")
        tmt = next(p for p in products if p["code"] == "TMT012")

        # Purchase Bill:
        # Line 1: 10 Boxes Screws @ Rs. 140/Box -> Taxable = 1,400. 1000 pcs base.
        # Line 2: 100 kg TMT @ Rs. 60/kg -> Taxable = 6,000. 100 kg base.
        # Total Taxable = 7,400.
        # Freight = 740 Rs.
        # Apportioned Freight Line 1 = 740 * (1400 / 7400) = 140 Rs.
        # Line 1 Landed Cost Base = (1400 + 140) / 1000 = 1.5400 Rs / piece.
        inv_number = f"INV-CFS-{uuid.uuid4().hex[:6].upper()}"
        bill_payload = {
            "supplier_name": "Coimbatore Fasteners & Steel Co",
            "supplier_invoice_number": inv_number,
            "godown_id": main_godown["id"],
            "freight_charges": 740.0,
            "loading_charges": 0.0,
            "other_expenses": 0.0,
            "round_off_amount": 0.0,
            "lines": [
                {
                    "product_id": screws["id"],
                    "unit_name": "Box",
                    "conversion_factor": 100,
                    "quantity": 10,
                    "unit_purchase_price": 140.0,
                    "discount_amount": 0.0,
                    "gst_rate_percent": 18.0,
                },
                {
                    "product_id": tmt["id"],
                    "unit_name": "kg",
                    "conversion_factor": 1,
                    "quantity": 100,
                    "unit_purchase_price": 60.0,
                    "discount_amount": 0.0,
                    "gst_rate_percent": 18.0,
                },
            ],
        }

        res_pb = await ac.post("/api/v1/inventory/purchases", json=bill_payload, headers=headers)
        assert res_pb.status_code == 201
        pb_data = res_pb.json()
        assert pb_data["supplier_invoice_number"] == inv_number
        assert len(pb_data["lines"]) == 2

        line_screws = next(l for l in pb_data["lines"] if l["product_id"] == screws["id"])
        assert line_screws["apportioned_overhead"] == "140.00"
        assert line_screws["landed_cost_base"] == "1.5400"

        # Check purchase listing
        res_list = await ac.get("/api/v1/inventory/purchases", headers=headers)
        assert res_list.status_code == 200
        assert any(b["supplier_invoice_number"] == inv_number for b in res_list.json())


@pytest.mark.asyncio
async def test_stock_adjustment_breakage_and_audit():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        godowns = (await ac.get("/api/v1/inventory/godowns", headers=headers)).json()
        main_godown = next(g for g in godowns if g["code"] == "MAIN")

        products = (await ac.get("/api/v1/inventory/products", headers=headers)).json()
        screws = next(p for p in products if p["code"] == "SCR001")

        # Record breakage of 15 pieces of screws (-15 pcs)
        adjustment_payload = {
            "godown_id": main_godown["id"],
            "reason_type": "BREAKAGE",
            "notes": "Damaged screws during bin re-arrangement",
            "lines": [
                {
                    "product_id": screws["id"],
                    "unit_name": "piece",
                    "conversion_factor": 1,
                    "quantity": -15,
                }
            ],
        }

        res_adj = await ac.post("/api/v1/inventory/adjustments", json=adjustment_payload, headers=headers)
        assert res_adj.status_code == 201
        adj_data = res_adj.json()
        assert adj_data["reason_type"] == "BREAKAGE"
        assert len(adj_data["lines"]) == 1
        assert adj_data["lines"][0]["quantity"] == "-15.0000"
        assert adj_data["lines"][0]["base_quantity"] == "-15.0000"

        # Check list adjustments
        res_list = await ac.get("/api/v1/inventory/adjustments", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1


@pytest.mark.asyncio
async def test_low_stock_alerts_detection():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    # Ensure TMT012 has min_stock_base higher than current stock to deterministically test alert
    async with async_session_factory() as session:
        tmt_p = await session.scalar(select(Product).where(Product.code == "TMT012", Product.tenant_id == DEMO_TENANT_ID))
        if tmt_p:
            tmt_p.min_stock_base = Decimal("50000.0000")
            await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res_alerts = await ac.get("/api/v1/inventory/alerts/low-stock", headers=headers)
        assert res_alerts.status_code == 200
        alerts = res_alerts.json()
        assert len(alerts) >= 1

        # TMT012 has min_stock_base = 50000 kg, current stock is <= 50000 kg
        tmt_alert = next((a for a in alerts if a["product_code"] == "TMT012"), None)
        assert tmt_alert is not None
        assert Decimal(tmt_alert["min_stock_base"]) == Decimal("50000.0000")
        assert tmt_alert["alert_severity"] in ("OUT_OF_STOCK", "CRITICAL_LOW", "LOW_STOCK")
        assert "kg" in tmt_alert["display_suggested_reorder"]


@pytest.mark.asyncio
async def test_product_price_history_and_update():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        products = (await ac.get("/api/v1/inventory/products", headers=headers)).json()
        screws = next(p for p in products if p["code"] == "SCR001")

        # 1. Fetch initial price history
        res_hist = await ac.get(f"/api/v1/inventory/products/{screws['id']}/price-history", headers=headers)
        assert res_hist.status_code == 200
        hist_data = res_hist.json()
        assert hist_data["product_code"] == "SCR001"

        # 2. Update price for Retail list
        # Find RETAIL price list from DB / parties / seed
        # Let's post a new price
        # First let's get the price list id from parties or create/query
        parties = (await ac.get("/api/v1/ledger/parties", headers=headers)).json()
        # Seeded price list exists: let's query via the update endpoint with a dummy or real price list ID
        # Let's seed or use a real price list
        # In seed_demo_data, retail_pl code is RETAIL. Let's find it.
        # Or let's test via direct price update
        from app.models.catalogue import PriceList
        from sqlalchemy import select
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            pl = (await session.execute(select(PriceList).where(PriceList.code == "RETAIL"))).scalar_one()
            retail_pl_id = pl.id

        update_payload = {
            "price_list_id": retail_pl_id,
            "unit_name": "Box",
            "price": 195.0,
            "min_allowed_price": 180.0,
        }
        res_upd = await ac.post(
            f"/api/v1/inventory/products/{screws['id']}/prices",
            json=update_payload,
            headers=headers,
        )
        assert res_upd.status_code == 200
        assert res_upd.json()["status"] == "success"

        # 3. Check price history has the new active price
        res_hist2 = await ac.get(f"/api/v1/inventory/products/{screws['id']}/price-history", headers=headers)
        assert res_hist2.status_code == 200
        hist2_data = res_hist2.json()
        assert len(hist2_data["selling_price_history"]) >= 1
        current_retail = next(
            p for p in hist2_data["selling_price_history"]
            if p["price_list_code"] == "RETAIL" and p["unit_name"] == "Box"
        )
        assert current_retail["price"] == "195.00"
        assert current_retail["is_current"] is True
