"""API integration tests for FastAPI backend."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.init_db import init_db, seed_demo_data

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "ok"


@pytest.mark.asyncio
async def test_list_products_with_units():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/inventory/products", headers=headers)
        assert response.status_code == 200
        products = response.json()
        assert len(products) >= 2

        screws = next((p for p in products if p["code"] == "SCR001"), None)
        assert screws is not None
        assert len(screws["units"]) >= 2
        unit_names = [u["unit_name"] for u in screws["units"]]
        assert "Box" in unit_names
        assert "piece" in unit_names


@pytest.mark.asyncio
async def test_calculate_bill_api():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    payload = {
        "place_of_supply_state_code": "33",
        "lines": [
            {
                "product_id": "p1",
                "product_code": "SCR001",
                "product_name": "SS Screws",
                "unit_name": "Box",
                "conversion_factor": 100,
                "quantity": 2,
                "unit_price": 185.0,
                "hsn_code": "7318",
                "gst_rate_percent": 18.0,
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/billing/calculate", json=payload, headers=headers)
        assert response.status_code == 200
        bill = response.json()
        assert bill["subtotal_taxable"] == "370.00"
        assert bill["cgst_total"] == "33.30"
        assert bill["sgst_total"] == "33.30"
        assert bill["grand_total"] == "437.00"


@pytest.mark.asyncio
async def test_receipt_preview_api():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    payload = {
        "invoice_number": "C1/26-27/0042",
        "lines": [
            {
                "product_id": "p1",
                "product_code": "SCR001",
                "product_name": "SS Screws",
                "unit_name": "Box",
                "conversion_factor": 100,
                "quantity": 2,
                "unit_price": 185.0,
                "hsn_code": "7318",
                "gst_rate_percent": 18.0,
            }
        ],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/billing/receipt-preview", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["invoice_number"] == "C1/26-27/0042"
        assert "upi://pay?" in data["upi_intent"]
        assert "NET TOTAL:" in data["receipt_text"]


@pytest.mark.asyncio
async def test_list_parties():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/ledger/parties", headers=headers)
        assert response.status_code == 200
        parties = response.json()
        assert len(parties) >= 1
        assert any(p["name"] == "Murugan Constructions" for p in parties)


@pytest.mark.asyncio
async def test_create_customer_party():
    headers = {"X-Tenant-ID": DEMO_TENANT_ID}
    payload = {
        "party_type": "CUSTOMER",
        "name": "Karthik Builders",
        "phone": "9876543210",
        "gstin": "33AAACK1234D1Z5",
        "state_code": "33",
        "credit_limit": "25000.00",
        "credit_days": 15,
        "opening_balance": "5000.00",
        "price_list_code": "CONTRACTOR",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/ledger/parties", json=payload, headers=headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Karthik Builders"
        assert data["phone"] == "9876543210"
        assert data["current_balance"] == "5000.00"
        assert data["credit_limit"] == "25000.00"
        assert data["credit_days"] == 15
        assert data["state_code"] == "33"

