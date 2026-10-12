"""Golden-file regression tests for defects found in the backend audit (October 2026).

Each test pins exact paisa / base-unit values (AGENTS.md section 5) for one fixed defect.
Every test creates its own uniquely-coded products and parties, so the suite is order independent.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import async_session_factory
from app.core.init_db import init_db, seed_demo_data
from app.models.catalogue import PriceList
from app.models.stock import StockMovement
from app.models.ledger import LedgerEntry, PaymentAllocation
from app.modules.inventory.excel_import import CatalogueImportEngine
from app.modules.reports.reports_service import ReportsService

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"
H = {"X-Tenant-ID": DEMO_TENANT_ID}


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


def _uid() -> str:
    return uuid.uuid4().hex[:8].upper()


async def _price_list_id(code: str) -> str:
    async with async_session_factory() as session:
        return await session.scalar(
            select(PriceList.id).where(PriceList.tenant_id == DEMO_TENANT_ID, PriceList.code == code)
        )


async def _godown(ac: AsyncClient, code: str = "MAIN") -> dict:
    godowns = (await ac.get("/api/v1/inventory/godowns", headers=H)).json()
    return next(g for g in godowns if g["code"] == code)


async def _wire_product(ac: AsyncClient, prices=None) -> dict:
    """Wire sold by metre, bought by Coil of 90 metres."""
    res = await ac.post("/api/v1/inventory/products", headers=H, json={
        "code": f"WIRE-{_uid()}",
        "name": "Finolex 1.5 sqmm Wire",
        "hsn_code": "8544",
        "base_unit": "metre",
        "units": [
            {"unit_name": "Coil", "conversion_factor": 90, "is_default_purchase_unit": True},
            {"unit_name": "metre", "conversion_factor": 1, "is_default_sales_unit": True},
        ],
        "prices": prices or [],
    })
    assert res.status_code == 201, res.text
    return res.json()


async def _purchase(ac, godown_id, product_id, qty, price, unit="Coil", factor=90, freight=0, loading=0):
    res = await ac.post("/api/v1/inventory/purchases", headers=H, json={
        "supplier_name": "Golden Supplier",
        "supplier_invoice_number": f"GS-{_uid()}",
        "godown_id": godown_id,
        "freight_charges": freight,
        "loading_charges": loading,
        "lines": [{"product_id": product_id, "unit_name": unit, "conversion_factor": factor,
                   "quantity": qty, "unit_purchase_price": price, "gst_rate_percent": 18}],
    })
    assert res.status_code == 201, res.text
    return res.json()


async def _stock_of(ac, godown_id, product_id) -> dict:
    rows = (await ac.get(f"/api/v1/inventory/godowns/{godown_id}/stock", headers=H)).json()
    return next(r for r in rows if r["product_id"] == product_id)


async def _party(ac, **kw) -> dict:
    body = {"name": f"Golden Party {_uid()}", "phone": "9000000000"}
    body.update(kw)
    res = await ac.post("/api/v1/ledger/parties", headers=H, json=body)
    assert res.status_code == 201, res.text
    return res.json()


# -----------------------------------------------------------------------------
# Billing: base units, GST, variable weight, pricing tiers, credit limit
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invoice_uses_catalogue_conversion_factor_for_stock():
    """2 Coil sold without a client conversion_factor must move 180 m, not 2 m."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        wire = await _wire_product(ac)
        await _purchase(ac, main["id"], wire["id"], qty=10, price=1800)

        res = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "lines": [
                {"product_id": wire["id"], "unit_name": "Coil", "quantity": 2, "unit_price": 2100, "gst_rate_percent": 18},
                {"product_id": wire["id"], "unit_name": "metre", "quantity": 37, "unit_price": 25, "gst_rate_percent": 18},
            ],
        })
        assert res.status_code == 201, res.text
        inv = res.json()
        assert Decimal(inv["lines"][0]["conversion_factor"]) == Decimal("90")
        assert Decimal(inv["lines"][0]["base_quantity"]) == Decimal("180.0000")
        # Golden totals: 4200 + 925 = 5125 taxable, CGST = SGST = 461.25, exact 6047.50 -> 6048.00 (+0.50)
        assert Decimal(inv["subtotal_amount"]) == Decimal("5125.00")
        assert Decimal(inv["cgst_amount"]) == Decimal("461.25")
        assert Decimal(inv["round_off_amount"]) == Decimal("0.50")
        assert inv["grand_total"] == "6048.00"

        stock = await _stock_of(ac, main["id"], wire["id"])
        assert Decimal(stock["current_quantity_base"]) == Decimal("683.0000")  # 900 - 180 - 37
        assert stock["display_stock"] == "7 Coil 53 metre (683 metre)"


@pytest.mark.asyncio
async def test_zero_rated_gst_line_is_not_taxed_at_18_percent():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        res = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 1, "unit_price": 100, "gst_rate_percent": 0}],
        })
        assert res.status_code == 201, res.text
        inv = res.json()
        assert Decimal(inv["total_tax_amount"]) == Decimal("0.00")
        assert Decimal(inv["grand_total"]) == Decimal("100.00")
        assert Decimal(inv["lines"][0]["gst_rate_percent"]) == Decimal("0")


@pytest.mark.asyncio
async def test_inter_state_invoice_uses_igst_golden():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        res = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "place_of_supply_state_code": "29",
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 3, "unit_price": 33.33,
                       "discount_type": "PERCENT", "discount_value": 5, "gst_rate_percent": 18}],
        })
        assert res.status_code == 201, res.text
        inv = res.json()
        # gross 99.99, disc round2(4.9995)=5.00, taxable 94.99, IGST round2(17.0982)=17.10, exact 112.09 -> 112.00
        assert Decimal(inv["lines"][0]["taxable_amount"]) == Decimal("94.99")
        assert Decimal(inv["igst_amount"]) == Decimal("17.10")
        assert Decimal(inv["cgst_amount"]) == Decimal("0.00")
        assert Decimal(inv["round_off_amount"]) == Decimal("-0.09")
        assert Decimal(inv["grand_total"]) == Decimal("112.00")


@pytest.mark.asyncio
async def test_variable_weight_moves_actual_weight_even_without_client_flag():
    """10 rods of TMT weighed at 104.2 kg must deduct exactly -104.2000 kg (spec acceptance test)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        created = await ac.post("/api/v1/inventory/products", headers=H, json={
            "code": f"TMT-{_uid()}", "name": "12mm TMT Bar", "hsn_code": "7214", "base_unit": "kg",
            "is_variable_weight": True,
            "units": [{"unit_name": "Rod", "conversion_factor": 10.65, "is_default_sales_unit": True},
                      {"unit_name": "kg", "conversion_factor": 1}],
        })
        assert created.status_code == 201, created.text
        tmt = created.json()
        res = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "lines": [{"product_id": tmt["id"], "unit_name": "Rod", "quantity": 10, "actual_weight_kg": 104.2,
                       "unit_price": 640, "gst_rate_percent": 18}],
        })
        assert res.status_code == 201, res.text
        inv = res.json()
        assert Decimal(inv["lines"][0]["base_quantity"]) == Decimal("104.2000")
        async with async_session_factory() as session:
            mv = await session.scalar(
                select(StockMovement).where(
                    StockMovement.tenant_id == DEMO_TENANT_ID, StockMovement.reference_doc_id == inv["id"]
                )
            )
            assert mv.quantity_base == Decimal("-104.2000")


@pytest.mark.asyncio
async def test_party_tier_price_list_applied_and_floor_price_enforced():
    contractor_pl = await _price_list_id("CONTRACTOR")
    retail_pl = await _price_list_id("RETAIL")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac, prices=[
            {"price_list_id": retail_pl, "unit_name": "metre", "price": 25, "min_allowed_price": 22},
            {"price_list_id": contractor_pl, "unit_name": "metre", "price": 23, "min_allowed_price": 21},
        ])
        mason = await _party(ac, price_list_code="CONTRACTOR")

        def bill(price, **extra):
            body = {"party_id": mason["id"], "customer_name": mason["name"], "payment_mode": "CASH",
                    "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10,
                               "unit_price": price, "gst_rate_percent": 18}]}
            body.update(extra)
            return body

        ok = await ac.post("/api/v1/billing/invoices", headers=H, json=bill(21.5))
        assert ok.status_code == 201, ok.text
        assert ok.json()["price_list_id"] == contractor_pl  # contractor tier, not retail
        assert "BELOW_FLOOR_PRICE" not in ok.json()["review_flags"]

        below = await ac.post("/api/v1/billing/invoices", headers=H, json=bill(15))
        assert below.status_code == 400
        assert "floor price" in below.json()["detail"]

        # owner_override alone is not trusted: the server verifies the owner PIN
        no_pin = await ac.post("/api/v1/billing/invoices", headers=H, json=bill(15, owner_override=True))
        assert no_pin.status_code == 403
        approved = await ac.post("/api/v1/billing/invoices", headers=H,
                                 json=bill(15, owner_override=True, owner_pin="1234"))
        assert approved.status_code == 201, approved.text
        assert "BELOW_FLOOR_PRICE" in approved.json()["review_flags"]


@pytest.mark.asyncio
async def test_credit_limit_blocks_online_credit_bill_but_flags_offline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        party = await _party(ac, credit_limit=1000, credit_days=15)

        def bill(**extra):
            body = {"party_id": party["id"], "customer_name": party["name"], "payment_mode": "CREDIT",
                    "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 40,
                               "unit_price": 25, "gst_rate_percent": 18}]}  # 1180.00 on credit
            body.update(extra)
            return body

        blocked = await ac.post("/api/v1/billing/invoices", headers=H, json=bill())
        assert blocked.status_code == 400
        assert "Credit limit exceeded" in blocked.json()["detail"]

        # A fully paid cash bill does not consume credit, so it is never blocked
        cash = await ac.post("/api/v1/billing/invoices", headers=H, json=bill(payment_mode="CASH"))
        assert cash.status_code == 201

        offline = await ac.post("/api/v1/billing/invoices", headers=H, json=bill(
            is_offline_created=True, invoice_number=f"C9/26-27/{_uid()}"))
        assert offline.status_code == 201
        assert "CREDIT_LIMIT_EXCEEDED" in offline.json()["review_flags"]

        parties = (await ac.get("/api/v1/ledger/parties", headers=H)).json()
        p = next(x for x in parties if x["id"] == party["id"])
        assert Decimal(p["current_balance"]) == Decimal("1180.00")


@pytest.mark.asyncio
async def test_counter_payment_is_allocated_so_paid_bills_are_not_open_dues():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        party = await _party(ac)
        line = [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10, "unit_price": 23, "gst_rate_percent": 18}]

        full = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": party["id"], "customer_name": party["name"], "payment_mode": "CASH", "lines": line})
        assert full.status_code == 201
        assert full.json()["grand_total"] == "271.00"  # 230 + 41.40 = 271.40 -> 271.00 (-0.40)

        part = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": party["id"], "customer_name": party["name"], "payment_mode": "CASH",
            "paid_amount": 200, "lines": line})
        assert part.status_code == 201

        dues = (await ac.get(f"/api/v1/ledger/parties/{party['id']}/dues", headers=H)).json()
        assert len(dues) == 1
        assert dues[0]["doc_number"] == part.json()["invoice_number"]
        assert Decimal(dues[0]["due_amount"]) == Decimal("71.00")

        ageing = (await ac.get(f"/api/v1/ledger/parties/{party['id']}/ageing", headers=H)).json()
        assert Decimal(ageing["bucket_0_30"]) == Decimal("71.00")
        assert Decimal(ageing["unallocated_advance"]) == Decimal("0.00")
        # Paisa integrity: sum(unpaid) - unallocated advances == current balance
        assert Decimal(ageing["bucket_0_30"]) - Decimal(ageing["unallocated_advance"]) == Decimal(ageing["current_balance"])

        # A later receipt must settle the genuinely open bill, not the already-paid one
        rec = (await ac.post("/api/v1/ledger/receipts", headers=H, json={
            "party_id": party["id"], "total_amount": 71, "payment_mode": "UPI"})).json()
        assert rec["allocations"][0]["invoice_number"] == part.json()["invoice_number"]
        assert Decimal(rec["party_current_balance"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_offline_sync_is_idempotent_and_flags_negative_stock():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        wire = await _wire_product(ac)
        number = f"C1/26-27/{_uid()}"
        bill = {"invoice_number": number, "payment_mode": "CASH",
                "offline_created_at": "2026-10-11T10:00:00Z",
                "lines": [{"product_id": wire["id"], "unit_name": "Coil", "quantity": 1, "unit_price": 2100, "gst_rate_percent": 18}]}

        first = await ac.post("/api/v1/billing/sync-invoices", headers=H, json=[bill])
        assert first.status_code == 200, first.text
        r1 = first.json()[0]
        assert r1["status"] == "SYNCED" and r1["invoice_number"] == number
        assert "NEGATIVE_STOCK_WARNING" in r1["review_flags"]

        again = await ac.post("/api/v1/billing/sync-invoices", headers=H, json=[bill])
        assert again.json()[0]["invoice_id"] == r1["invoice_id"]

        stock = await _stock_of(ac, main["id"], wire["id"])
        assert Decimal(stock["current_quantity_base"]) == Decimal("-90.0000")  # deducted exactly once

        dup_online = await ac.post("/api/v1/billing/invoices", headers=H, json={**bill, "is_offline_created": False})
        assert dup_online.status_code == 400


@pytest.mark.asyncio
async def test_two_lines_same_product_in_godown_without_balance_row():
    """Second godown has no stock_balance row yet: two lines of one product must not crash (was 500)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        bypass = await _godown(ac, "BYPASS")
        wire = await _wire_product(ac)
        res = await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH", "godown_id": bypass["id"],
            "lines": [
                {"product_id": wire["id"], "unit_name": "metre", "quantity": 5, "unit_price": 25, "gst_rate_percent": 18},
                {"product_id": wire["id"], "unit_name": "metre", "quantity": 7, "unit_price": 25, "gst_rate_percent": 18},
            ],
        })
        assert res.status_code == 201, res.text
        stock = await _stock_of(ac, bypass["id"], wire["id"])
        assert Decimal(stock["current_quantity_base"]) == Decimal("-12.0000")


# -----------------------------------------------------------------------------
# Inventory: WAC, landed cost, cost of goods sold
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_freight_apportionment_sums_exactly_and_wac_golden():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        products = [await _wire_product(ac) for _ in range(3)]
        res = await ac.post("/api/v1/inventory/purchases", headers=H, json={
            "supplier_name": "Golden Supplier", "supplier_invoice_number": f"GS-{_uid()}",
            "godown_id": main["id"], "freight_charges": 70, "loading_charges": 30,
            "lines": [{"product_id": p["id"], "unit_name": "metre", "conversion_factor": 1, "quantity": 10,
                       "unit_purchase_price": 10} for p in products],
        })
        assert res.status_code == 201, res.text
        lines = res.json()["lines"]
        overheads = [Decimal(l["apportioned_overhead"]) for l in lines]
        assert overheads == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        assert sum(overheads) == Decimal("100.00")
        # landed cost per metre = (100 + 33.34) / 10 = 13.334
        assert Decimal(lines[2]["landed_cost_base"]) == Decimal("13.3340")


@pytest.mark.asyncio
async def test_cost_at_sale_uses_weighted_average_cost_not_last_purchase():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        wire = await _wire_product(ac)
        # 900 m @ (18000+400)/900 = 20.4444 ; then 900 m @ 2160/90 = 24.0000
        await _purchase(ac, main["id"], wire["id"], qty=10, price=1800, freight=300, loading=100)
        await _purchase(ac, main["id"], wire["id"], qty=10, price=2160)
        stock = await _stock_of(ac, main["id"], wire["id"])
        # WAC = (900*20.4444 + 900*24.0000) / 1800 = 22.2222
        assert Decimal(stock["weighted_avg_cost_base"]) == Decimal("22.2222")

        inv = (await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10, "unit_price": 30, "gst_rate_percent": 18}],
        })).json()
        assert Decimal(inv["lines"][0]["cost_price_base_at_sale"]) == Decimal("22.2222")


@pytest.mark.asyncio
async def test_sales_return_restocks_at_cost_not_selling_price():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        wire = await _wire_product(ac)
        await _purchase(ac, main["id"], wire["id"], qty=10, price=1800)  # WAC 20.0000
        ret = await ac.post("/api/v1/billing/returns", headers=H, json={
            "refund_mode": "CASH", "godown_id": main["id"],
            "lines": [{"product_id": wire["id"], "unit_name": "Coil", "quantity": 1, "unit_price": 2100, "gst_rate_percent": 18}],
        })
        assert ret.status_code == 201, ret.text
        assert Decimal(ret.json()["lines"][0]["base_quantity"]) == Decimal("90.0000")
        async with async_session_factory() as session:
            mv = await session.scalar(
                select(StockMovement).where(StockMovement.reference_doc_id == ret.json()["id"])
            )
            assert mv.unit_cost_base == Decimal("20.0000")
        stock = await _stock_of(ac, main["id"], wire["id"])
        assert Decimal(stock["current_quantity_base"]) == Decimal("990.0000")
        assert Decimal(stock["weighted_avg_cost_base"]) == Decimal("20.0000")


@pytest.mark.asyncio
async def test_duplicate_product_code_and_purchase_number_return_400_not_500():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        wire = await _wire_product(ac)
        dup = await ac.post("/api/v1/inventory/products", headers=H, json={
            "code": wire["code"], "name": "dup", "hsn_code": "8544", "base_unit": "metre"})
        assert dup.status_code == 400

        pur = await _purchase(ac, main["id"], wire["id"], qty=1, price=100)
        # Same supplier (identified by name when there is no supplier_id) + same number -> duplicate
        again = await ac.post("/api/v1/inventory/purchases", headers=H, json={
            "supplier_name": "Golden Supplier", "supplier_invoice_number": pur["supplier_invoice_number"],
            "godown_id": main["id"],
            "lines": [{"product_id": wire["id"], "unit_name": "Coil", "conversion_factor": 90, "quantity": 1, "unit_purchase_price": 1}]})
        assert again.status_code == 400


@pytest.mark.asyncio
async def test_search_uses_current_price_not_archived_one():
    retail_pl = await _price_list_id("RETAIL")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac, prices=[{"price_list_id": retail_pl, "unit_name": "metre", "price": 25}])
        upd = await ac.post(f"/api/v1/inventory/products/{wire['id']}/prices", headers=H,
                            json={"price_list_id": retail_pl, "unit_name": "metre", "price": 27})
        assert upd.status_code == 200
        hit = (await ac.get(f"/api/v1/billing/search?q={wire['code']}", headers=H)).json()[0]
        metre = next(u for u in hit["units"] if u["unit_name"] == "metre")
        assert Decimal(metre["selling_price"]) == Decimal("27.00")


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_daily_sales_taxable_is_not_double_discounted():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        before = (await ac.get("/api/v1/reports/sales/daily", headers=H)).json()
        inv = (await ac.post("/api/v1/billing/invoices", headers=H, json={
            "payment_mode": "CASH",
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10, "unit_price": 25,
                       "discount_type": "FLAT", "discount_value": 20, "gst_rate_percent": 18}],
        })).json()
        assert Decimal(inv["subtotal_amount"]) == Decimal("230.00")
        after = (await ac.get("/api/v1/reports/sales/daily", headers=H)).json()
        delta = Decimal(after["taxable_amount"]) - Decimal(before["taxable_amount"])
        assert delta == Decimal("230.00")


@pytest.mark.asyncio
async def test_cash_reconcile_counts_counter_payments_once_and_only_cash_receipts():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        party = await _party(ac)
        base = (await ac.post("/api/v1/reports/cash/reconcile", headers=H, json={"actual_cash_counted": 0})).json()

        await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": party["id"], "customer_name": party["name"], "payment_mode": "CASH",
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10, "unit_price": 23, "gst_rate_percent": 18}]})
        await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": party["id"], "customer_name": party["name"], "payment_mode": "SPLIT", "paid_amount": 271,
            "payment_breakdown": {"CASH": 100, "UPI": 171},
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 10, "unit_price": 23, "gst_rate_percent": 18}]})
        await ac.post("/api/v1/ledger/receipts", headers=H, json={
            "party_id": party["id"], "total_amount": 1000, "payment_mode": "CASH", "notes": "Old dues settled"})
        await ac.post("/api/v1/ledger/receipts", headers=H, json={
            "party_id": party["id"], "total_amount": 500, "payment_mode": "UPI", "notes": "cash promised later"})

        after = (await ac.post("/api/v1/reports/cash/reconcile", headers=H, json={"actual_cash_counted": 0})).json()
        assert Decimal(after["cash_sales_amount"]) - Decimal(base["cash_sales_amount"]) == Decimal("371.00")
        assert Decimal(after["cash_ledger_receipts"]) - Decimal(base["cash_ledger_receipts"]) == Decimal("1000.00")


def test_split_cash_portion_parsing():
    assert ReportsService._split_cash_portion({"CASH": 500, "UPI": 300}, Decimal("800")) == Decimal("500.00")
    assert ReportsService._split_cash_portion(
        [{"mode": "CASH", "amount": 120.5}, {"mode": "UPI", "amount": 79.5}], Decimal("200")) == Decimal("120.50")
    assert ReportsService._split_cash_portion(
        {"payments": [{"mode": "UPI", "amount": 200}]}, Decimal("200")) == Decimal("0.00")
    assert ReportsService._split_cash_portion(None, Decimal("200")) == Decimal("200")


@pytest.mark.asyncio
async def test_stock_valuation_uses_each_godowns_own_wac():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        bypass = await _godown(ac, "BYPASS")
        wire = await _wire_product(ac)
        await _purchase(ac, main["id"], wire["id"], qty=1, price=1800)    # 90 m @ 20
        await _purchase(ac, bypass["id"], wire["id"], qty=2, price=2700)  # 180 m @ 30
        data = (await ac.get("/api/v1/reports/stock/valuation", headers=H)).json()
        item = next(i for i in data["items"] if i["product_id"] == wire["id"])
        # 90*20 + 180*30 = 1800 + 5400 = 7200 (old code valued all 270 m at 20 -> 5400)
        assert Decimal(item["valuation_cost"]) == Decimal("7200.00")
        assert Decimal(item["wac_base"]) == Decimal("26.6667")


# -----------------------------------------------------------------------------
# AI assistant tenancy & filters
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_query_cannot_switch_tenant_via_body():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        foreign = await ac.post("/api/v1/ai/query", headers=H, json={
            "query": "Who owes me money?", "tenant_id": "11111111-1111-1111-1111-111111111111"})
        assert foreign.status_code == 403
        same = await ac.post("/api/v1/ai/query", headers=H, json={"query": "Who owes me money?", "tenant_id": DEMO_TENANT_ID})
        assert same.status_code == 200


@pytest.mark.asyncio
async def test_ai_receivables_min_days_uses_real_bill_age():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        old = await _party(ac, credit_days=0)
        fresh = await _party(ac, credit_days=0)
        line = [{"product_id": wire["id"], "unit_name": "metre", "quantity": 4, "unit_price": 25, "gst_rate_percent": 18}]
        await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": old["id"], "customer_name": old["name"], "payment_mode": "CREDIT",
            "invoice_date": (datetime.now(timezone.utc) - timedelta(days=75)).isoformat(), "lines": line})
        await ac.post("/api/v1/billing/invoices", headers=H, json={
            "party_id": fresh["id"], "customer_name": fresh["name"], "payment_mode": "CREDIT", "lines": line})

        res = (await ac.post("/api/v1/ai/query", headers=H, json={"query": "Who owes me money for over 60 days?"})).json()
        assert res["tool_called"] == "get_receivables"
        ids = {d["party_id"] for d in res["raw_data"]["debtors"]}
        assert old["id"] in ids
        assert fresh["id"] not in ids  # overdue (credit_days=0) but only a few days old

        ageing = (await ac.get(f"/api/v1/ledger/parties/{old['id']}/ageing", headers=H)).json()
        assert Decimal(ageing["bucket_61_90"]) == Decimal("118.00")


# -----------------------------------------------------------------------------
# Bulk import
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_catalogue_reimport_does_not_crash_and_opening_stock_accumulates():
    code = f"IMP{_uid()}"
    csv_text = (
        "code,name,category,hsn_code,base_unit,purchase_price,selling_price_retail,selling_price_wholesale,"
        "packing_unit,packing_factor,opening_stock_base\n"
        f"{code},Anchor Fastener,Fasteners,7318,piece,2.00,3.00,2.60,Box,100,500\n"
    )
    rows, errors = CatalogueImportEngine.parse_csv_stream(csv_text)
    assert errors == []
    async with async_session_factory() as session:
        first = await CatalogueImportEngine.commit_catalogue(DEMO_TENANT_ID, rows, session)
        assert first["prices_created"] == 2  # retail + wholesale
    async with async_session_factory() as session:
        second = await CatalogueImportEngine.commit_catalogue(DEMO_TENANT_ID, rows, session)
        assert second["products_updated"] == 1

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        main = await _godown(ac)
        prod = (await ac.get(f"/api/v1/billing/search?q={code}", headers=H)).json()[0]
        stock = await _stock_of(ac, main["id"], prod["id"])
        assert Decimal(stock["current_quantity_base"]) == Decimal("1000.0000")  # two OPENING movements of 500
        assert stock["display_stock"] == "10 Box (1000 piece)"


@pytest.mark.asyncio
async def test_server_numbering_skips_numbers_already_used_by_offline_sync():
    """Counter 1 synced C1/26-27/{n+1} offline; the next server-issued number must not collide (was 500)."""
    from app.models.tenant import NumberSeries

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        line = [{"product_id": wire["id"], "unit_name": "metre", "quantity": 1, "unit_price": 10, "gst_rate_percent": 18}]
        first = (await ac.post("/api/v1/billing/invoices", headers=H, json={"payment_mode": "CASH", "lines": line})).json()
        async with async_session_factory() as session:
            series = await session.scalar(
                select(NumberSeries).where(NumberSeries.tenant_id == DEMO_TENANT_ID, NumberSeries.doc_type == "SALES_INVOICE")
            )
            prefix, n = series.prefix, series.current_number
        assert first["invoice_number"] == f"{prefix}{n:04d}"

        synced = await ac.post("/api/v1/billing/sync-invoices", headers=H, json=[
            {"invoice_number": f"{prefix}{n + 1:04d}", "payment_mode": "CASH", "lines": line}])
        assert synced.json()[0]["status"] == "SYNCED"

        nxt = await ac.post("/api/v1/billing/invoices", headers=H, json={"payment_mode": "CASH", "lines": line})
        assert nxt.status_code == 201, nxt.text
        assert nxt.json()["invoice_number"] == f"{prefix}{n + 2:04d}"


@pytest.mark.asyncio
async def test_quotation_for_party_uses_party_price_tier():
    wholesale_pl = await _price_list_id("WHOLESALE")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        wire = await _wire_product(ac)
        dealer = await _party(ac, price_list_code="WHOLESALE")
        q = await ac.post("/api/v1/billing/quotations", headers=H, json={
            "party_id": dealer["id"], "customer_name": dealer["name"],
            "lines": [{"product_id": wire["id"], "unit_name": "metre", "quantity": 1, "unit_price": 20}]})
        assert q.status_code == 201
        assert q.json()["price_list_id"] == wholesale_pl
