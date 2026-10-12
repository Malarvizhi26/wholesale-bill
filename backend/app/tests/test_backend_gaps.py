"""Golden-file tests for the backend gap fixes (October 2026).

Covers: server-side owner PIN, mandatory tenant header + RLS DDL/migrations, persisted review flags,
IST business days, Excel/CSV import route, product GST slab, party price-list code, cash refunds in
the drawer, credit-note allocation, per-supplier purchase numbers, supplier dues, call list, price lists.

A second tenant (TENANT_B) is used both for tenant A vs tenant B leak tests and for date-pinned
golden figures that must not be polluted by other tests' "today" invoices.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.core.database import Base, async_session_factory
from app.core.init_db import DEMO_TENANT_ID, init_db, seed_demo_data
from app.core.rls_policies import all_rls_statements, rls_statements, tenant_scoped_tables
from app.core.security import clear_pin_failures, hash_pin, verify_pin
from app.core.timeutils import ist_date_of, ist_day_bounds_utc
from app.models.catalogue import PriceList
from app.models.ledger import LedgerEntry, PaymentAllocation
from app.models.stock import Godown, StockAlert
from app.models.tenant import Tenant
from app.modules.ledger.ledger_service import LedgerService

TENANT_B = "00000000-0000-0000-0000-00000000000b"
HA = {"X-Tenant-ID": DEMO_TENANT_ID}
HB = {"X-Tenant-ID": TENANT_B}
DEMO_PIN = "1234"
B_PIN = "4321"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()
    async with async_session_factory() as session:
        if not await session.scalar(select(Tenant.id).where(Tenant.id == TENANT_B)):
            session.add(Tenant(
                id=TENANT_B, business_name="Tenant B Traders", phone="9000000001",
                address_line1="1 Test Street", city="Madurai", state_code="33", pincode="625001",
                owner_pin_hash=hash_pin(B_PIN),
            ))
            session.add(Godown(tenant_id=TENANT_B, code="MAIN", name="B Main", is_primary=True))
            session.add(PriceList(tenant_id=TENANT_B, code="RETAIL", name="B Retail", is_default=True))
            await session.commit()
    clear_pin_failures(DEMO_TENANT_ID)
    clear_pin_failures(TENANT_B)


def _uid() -> str:
    return uuid.uuid4().hex[:8].upper()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _godown_id(ac, headers) -> str:
    rows = (await ac.get("/api/v1/inventory/godowns", headers=headers)).json()
    return next(g for g in rows if g["code"] == "MAIN")["id"]


async def _product(ac, headers, gst=None, prices=None, code_prefix="P") -> dict:
    body = {
        "code": f"{code_prefix}-{_uid()}", "name": "Asian Paints Primer 1L", "hsn_code": "3208",
        "base_unit": "piece",
        "units": [{"unit_name": "Box", "conversion_factor": 10},
                  {"unit_name": "piece", "conversion_factor": 1, "is_default_sales_unit": True}],
        "prices": prices or [],
    }
    if gst is not None:
        body["gst_rate_percent"] = gst
    res = await ac.post("/api/v1/inventory/products", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


async def _purchase(ac, headers, godown_id, product_id, qty, price, supplier_id=None,
                    supplier_name="Gap Supplier", number=None, bill_date=None):
    body = {
        "supplier_id": supplier_id, "supplier_name": supplier_name,
        "supplier_invoice_number": number or f"SI-{_uid()}", "godown_id": godown_id,
        "lines": [{"product_id": product_id, "unit_name": "piece", "conversion_factor": 1,
                   "quantity": qty, "unit_purchase_price": price}],
    }
    if bill_date:
        body["bill_date"] = bill_date
    return await ac.post("/api/v1/inventory/purchases", headers=headers, json=body)


async def _party(ac, headers, **kw) -> dict:
    body = {"name": f"Gap Party {_uid()}", "phone": "9000000000"}
    body.update(kw)
    res = await ac.post("/api/v1/ledger/parties", headers=headers, json=body)
    assert res.status_code == 201, res.text
    return res.json()


async def _invoice(ac, headers, lines, **kw):
    body = {"payment_mode": "CASH", "lines": lines}
    body.update(kw)
    return await ac.post("/api/v1/billing/invoices", headers=headers, json=body)


async def _assert_balance_invariant(tenant_id: str, party_id: str) -> dict:
    """AGENTS.md: sum(unpaid invoices) - unallocated advances == party.current_balance."""
    async with async_session_factory() as session:
        ageing = await LedgerService.get_party_ageing_summary(session, tenant_id, party_id)
    unpaid = sum((i.due_amount for i in ageing.open_invoices), Decimal("0.00"))
    assert unpaid - ageing.unallocated_advance == ageing.current_balance
    return {"unpaid": unpaid, "advance": ageing.unallocated_advance, "balance": ageing.current_balance}


# =============================================================================
# 1. Owner PIN on the server
# =============================================================================

def test_pin_hash_is_salted_pbkdf2_and_constant_time_verified():
    h1, h2 = hash_pin("1234"), hash_pin("1234")
    assert h1.startswith("pbkdf2_sha256$") and "1234" not in h1.split("$", 2)[2]
    assert h1 != h2  # random salt
    assert verify_pin("1234", h1) and verify_pin("1234", h2)
    assert not verify_pin("1235", h1)
    assert not verify_pin(None, h1) and not verify_pin("1234", None) and not verify_pin("1234", "garbage")
    with pytest.raises(ValueError):
        hash_pin("12a4")


@pytest.mark.asyncio
async def test_verify_pin_endpoint_and_tenant_isolation():
    async with _client() as ac:
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HA, json={"pin": DEMO_PIN})).json() == {"valid": True}
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HA, json={"pin": "0000"})).json() == {"valid": False}
        # Tenant B's PIN never unlocks tenant A and vice versa
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HA, json={"pin": B_PIN})).json() == {"valid": False}
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": DEMO_PIN})).json() == {"valid": False}
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": B_PIN})).json() == {"valid": True}
    async with async_session_factory() as session:
        stored = await session.scalar(select(Tenant.owner_pin_hash).where(Tenant.id == DEMO_TENANT_ID))
        assert stored.startswith("pbkdf2_sha256$")


@pytest.mark.asyncio
async def test_change_pin_requires_current_pin():
    async with _client() as ac:
        bad = await ac.post("/api/v1/auth/change-pin", headers=HB, json={"current_pin": "9999", "new_pin": "5678"})
        assert bad.status_code == 403
        weak = await ac.post("/api/v1/auth/change-pin", headers=HB, json={"current_pin": B_PIN, "new_pin": "12"})
        assert weak.status_code == 422
        ok = await ac.post("/api/v1/auth/change-pin", headers=HB, json={"current_pin": B_PIN, "new_pin": "5678"})
        assert ok.status_code == 200 and ok.json() == {"status": "ok"}
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": "5678"})).json()["valid"] is True
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": B_PIN})).json()["valid"] is False
        # restore for the other tests
        back = await ac.post("/api/v1/auth/change-pin", headers=HB, json={"current_pin": "5678", "new_pin": B_PIN})
        assert back.status_code == 200


@pytest.mark.asyncio
async def test_wrong_pin_attempts_are_throttled():
    async with _client() as ac:
        for _ in range(5):
            r = await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": "0000"})
            assert r.status_code == 200 and r.json()["valid"] is False
        locked = await ac.post("/api/v1/auth/verify-pin", headers=HB, json={"pin": B_PIN})
        assert locked.status_code == 429
        # the lockout is per tenant
        assert (await ac.post("/api/v1/auth/verify-pin", headers=HA, json={"pin": DEMO_PIN})).json()["valid"] is True
    clear_pin_failures(TENANT_B)


@pytest.mark.asyncio
async def test_owner_override_needs_valid_pin_online_but_offline_sync_never_rejected():
    retail = None
    async with async_session_factory() as session:
        retail = await session.scalar(
            select(PriceList.id).where(PriceList.tenant_id == DEMO_TENANT_ID, PriceList.code == "RETAIL"))
    async with _client() as ac:
        prod = await _product(ac, HA, prices=[{"price_list_id": retail, "unit_name": "piece", "price": 100,
                                                "min_allowed_price": 90}])
        line = [{"product_id": prod["id"], "unit_name": "piece", "quantity": 1, "unit_price": 50, "gst_rate_percent": 18}]

        assert (await _invoice(ac, HA, line)).status_code == 400  # below floor, no override
        assert (await _invoice(ac, HA, line, owner_override=True)).status_code == 403
        assert (await _invoice(ac, HA, line, owner_override=True, owner_pin="9999")).status_code == 403
        ok = await _invoice(ac, HA, line, owner_override=True, owner_pin=DEMO_PIN)
        assert ok.status_code == 201
        assert "BELOW_FLOOR_PRICE" in ok.json()["review_flags"]
        assert "owner_pin" not in ok.json()

        # Offline sync with a wrong PIN: still accepted, flagged, and not recorded as owner-approved
        num = f"C9/26-27/{_uid()}"
        sync = await ac.post("/api/v1/billing/sync-invoices", headers=HA, json=[{
            "invoice_number": num, "owner_override": True, "owner_pin": "0000", "lines": line}])
        assert sync.status_code == 200
        assert sync.json()[0]["status"] == "SYNCED"
        assert "BELOW_FLOOR_PRICE" in sync.json()[0]["review_flags"]

    async with async_session_factory() as session:
        online_flag = await session.scalar(select(StockAlert).where(StockAlert.reference_doc_id == ok.json()["id"]))
        assert online_flag.alert_type == "BELOW_FLOOR_PRICE" and online_flag.owner_override is True
        offline_flag = await session.scalar(
            select(StockAlert).where(StockAlert.reference_doc_number == num, StockAlert.alert_type == "BELOW_FLOOR_PRICE"))
        assert offline_flag.is_offline_created is True and offline_flag.owner_override is False


# =============================================================================
# 2. Tenant isolation: mandatory header + PostgreSQL RLS
# =============================================================================

@pytest.mark.asyncio
async def test_missing_or_malformed_tenant_header_is_400():
    async with _client() as ac:
        for path in ("/api/v1/inventory/products", "/api/v1/billing/review-flags",
                     "/api/v1/inventory/price-lists", "/api/v1/ledger/parties"):
            missing = await ac.get(path)
            assert missing.status_code == 400, path
            assert "X-Tenant-ID" in missing.json()["detail"]
            bad = await ac.get(path, headers={"X-Tenant-ID": "not-a-uuid"})
            assert bad.status_code == 400
        assert (await ac.post("/api/v1/auth/verify-pin", json={"pin": DEMO_PIN})).status_code == 400


def test_rls_policy_ddl_golden():
    assert rls_statements("parties") == [
        "ALTER TABLE parties ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE parties FORCE ROW LEVEL SECURITY",
        "DROP POLICY IF EXISTS tenant_isolation ON parties",
        "CREATE POLICY tenant_isolation ON parties USING "
        "(tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')) WITH CHECK "
        "(tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))",
    ]
    tables = tenant_scoped_tables(Base.metadata)
    assert "stock_alerts" in tables and "sales_invoices" in tables and "tenants" not in tables
    stmts = all_rls_statements(tables)
    assert len(stmts) == 4 * (len(tables) + 1)
    assert "CREATE POLICY tenant_isolation ON tenants USING (id = " in stmts[-1]


def test_migration_rls_table_list_matches_models():
    """The migration hard-codes its RLS table list; it must cover every tenant-scoped table."""
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions", "0002_owner_pin_review_flags_rls.py")
    spec = importlib.util.spec_from_file_location("mig0002", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert sorted(mod.TENANT_TABLES) == tenant_scoped_tables(Base.metadata)


def test_alembic_upgrade_head_matches_models(tmp_path):
    """alembic upgrade head on an empty SQLite DB yields exactly the ORM schema (no pending diff)."""
    from alembic import command
    from alembic.config import Config
    from alembic.util.exc import AutogenerateDiffsDetected

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{(tmp_path / 'mig.db').as_posix()}")
    command.upgrade(cfg, "head")
    try:
        command.check(cfg)
    except AutogenerateDiffsDetected as e:  # pragma: no cover
        pytest.fail(f"Models and migrations differ: {e}")
    command.downgrade(cfg, "base")


def test_legacy_sqlite_db_is_upgraded_in_place_at_startup(tmp_path):
    """A desktop SQLite DB created by an older build gains the new columns and the per-supplier
    purchase-bill constraint without losing rows (alembic 0001 == the pre-change schema)."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from app.core.init_db import _add_missing_sqlite_columns

    db = (tmp_path / "legacy.db").as_posix()
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db}")
    command.upgrade(cfg, "0001_baseline")

    engine = create_engine(f"sqlite:///{db}")
    now = "2026-10-01 00:00:00.000000"
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO purchase_bills (id, tenant_id, supplier_name, supplier_invoice_number, bill_date, godown_id, "
            "subtotal_taxable, total_tax_amount, freight_charges, loading_charges, other_expenses, round_off_amount, "
            "total_invoice_amount, created_at, updated_at) VALUES ('b1', 't1', 'Old', 'INV-1', :n, 'g1', 0, 0, 0, 0, 0, 0, "
            "100, :n, :n)"), {"n": now})
    with engine.begin() as conn:
        _add_missing_sqlite_columns(conn)
    with engine.begin() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("products")}
        assert "gst_rate_percent" in cols
        assert "owner_pin_hash" in {c["name"] for c in inspect(conn).get_columns("tenants")}
        ddl = conn.execute(text("SELECT sql FROM sqlite_master WHERE name = 'purchase_bills'")).scalar()
        assert "uq_purchase_bill_supplier_invoice" in ddl and "uq_purchase_bill_invoice_number" not in ddl
        assert conn.execute(text("SELECT total_invoice_amount FROM purchase_bills WHERE id = 'b1'")).scalar() == 100
    engine.dispose()


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="set TEST_POSTGRES_URL (non-superuser role) to run")
def test_postgres_rls_blocks_cross_tenant_reads():  # pragma: no cover - needs a live PostgreSQL
    import asyncio
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ["TEST_POSTGRES_URL"]
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    async def run():
        engine = create_async_engine(url)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        async with engine.begin() as conn:
            forced = (await conn.execute(text(
                "SELECT count(*) FROM pg_class WHERE relname = 'parties' AND relrowsecurity AND relforcerowsecurity"
            ))).scalar()
            assert forced == 1
            await conn.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": a})
            await conn.execute(text(
                "INSERT INTO price_lists (id, tenant_id, code, name, is_default, created_at, updated_at) "
                "VALUES (:id, :t, 'RLS', 'RLS test', false, now(), now())"), {"id": str(uuid.uuid4()), "t": a})
        async with engine.begin() as conn:
            await conn.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": b})
            seen = (await conn.execute(text("SELECT count(*) FROM price_lists WHERE tenant_id = :t"), {"t": a})).scalar()
            assert seen == 0
        await engine.dispose()

    asyncio.run(run())


# =============================================================================
# 3. Persisted review flags
# =============================================================================

@pytest.mark.asyncio
async def test_negative_stock_and_credit_limit_flags_are_persisted_and_resolvable():
    async with _client() as ac:
        prod = await _product(ac, HA)  # zero stock
        party = await _party(ac, HA, credit_limit=100, credit_days=10)
        num = f"C8/26-27/{_uid()}"
        sync = await ac.post("/api/v1/billing/sync-invoices", headers=HA, json=[{
            "invoice_number": num, "party_id": party["id"], "customer_name": party["name"], "payment_mode": "CREDIT",
            "lines": [{"product_id": prod["id"], "unit_name": "Box", "quantity": 2, "unit_price": 100, "gst_rate_percent": 18}],
        }])
        assert sync.json()[0]["status"] == "SYNCED"
        assert set(sync.json()[0]["review_flags"]) == {"NEGATIVE_STOCK_WARNING", "CREDIT_LIMIT_EXCEEDED"}

        flags = (await ac.get("/api/v1/billing/review-flags", headers=HA)).json()
        mine = [f for f in flags if f["reference_doc_number"] == num]
        assert {f["alert_type"] for f in mine} == {"NEGATIVE_STOCK_WARNING", "CREDIT_LIMIT_EXCEEDED"}
        neg = next(f for f in mine if f["alert_type"] == "NEGATIVE_STOCK_WARNING")
        assert neg["status"] == "OPEN" and neg["product_id"] == prod["id"] and neg["is_offline_created"] is True
        assert "-20.0000" in neg["message"]  # 2 Box x 10 = 20 pieces below zero

        # Re-sending the same offline bill is idempotent: no duplicate flags
        await ac.post("/api/v1/billing/sync-invoices", headers=HA, json=[{
            "invoice_number": num, "party_id": party["id"], "customer_name": party["name"], "payment_mode": "CREDIT",
            "lines": [{"product_id": prod["id"], "unit_name": "Box", "quantity": 2, "unit_price": 100}],
        }])
        again = [f for f in (await ac.get("/api/v1/billing/review-flags", headers=HA)).json()
                 if f["reference_doc_number"] == num]
        assert len(again) == 2

        # Tenant B can neither see nor resolve tenant A's flags
        b_flags = (await ac.get("/api/v1/billing/review-flags?status=ALL", headers=HB)).json()
        assert all(f["reference_doc_number"] != num for f in b_flags)
        cross = await ac.post(f"/api/v1/billing/review-flags/{neg['id']}/resolve", headers=HB, json={"owner_pin": B_PIN})
        assert cross.status_code == 404

        no_pin = await ac.post(f"/api/v1/billing/review-flags/{neg['id']}/resolve", headers=HA, json={"owner_pin": "0000"})
        assert no_pin.status_code == 403
        done = await ac.post(f"/api/v1/billing/review-flags/{neg['id']}/resolve", headers=HA,
                             json={"owner_pin": DEMO_PIN, "notes": "Stock count done"})
        assert done.status_code == 200
        assert done.json()["status"] == "RESOLVED" and done.json()["resolution_notes"] == "Stock count done"
        assert done.json()["resolved_at"] is not None
        twice = await ac.post(f"/api/v1/billing/review-flags/{neg['id']}/resolve", headers=HA, json={"owner_pin": DEMO_PIN})
        assert twice.status_code == 409

        open_ids = {f["id"] for f in (await ac.get("/api/v1/billing/review-flags", headers=HA)).json()}
        resolved_ids = {f["id"] for f in (await ac.get("/api/v1/billing/review-flags?status=RESOLVED", headers=HA)).json()}
        assert neg["id"] not in open_ids and neg["id"] in resolved_ids


# =============================================================================
# 4. IST business days
# =============================================================================

def test_ist_day_bounds_golden():
    start, end = ist_day_bounds_utc(date(2026, 10, 12))
    assert start == datetime(2026, 10, 11, 18, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 12, 18, 30, tzinfo=timezone.utc)
    assert ist_date_of(datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc)) == date(2026, 10, 12)
    assert ist_date_of(datetime(2026, 10, 11, 18, 29)) == date(2026, 10, 11)  # naive = UTC


@pytest.mark.asyncio
async def test_after_midnight_ist_sale_counts_on_the_ist_day():
    async with _client() as ac:
        prod = await _product(ac, HB)
        party = await _party(ac, HB)
        # 00:30 IST on 15-Jan-2025 == 19:00 UTC on 14-Jan-2025
        res = await _invoice(ac, HB, [{"product_id": prod["id"], "unit_name": "piece", "quantity": 1,
                                       "unit_price": 1000, "gst_rate_percent": 18}],
                             invoice_date="2025-01-14T19:00:00Z", party_id=party["id"], customer_name=party["name"])
        assert res.status_code == 201, res.text

        d15 = (await ac.get("/api/v1/reports/sales/daily?start_date=2025-01-15", headers=HB)).json()
        assert d15["total_invoices"] == 1 and Decimal(d15["grand_total"]) == Decimal("1180.00")
        assert d15["hourly_breakdown"] == [{"hour": "00:00", "invoice_count": 1, "total_sales": "1180.00"}]
        d14 = (await ac.get("/api/v1/reports/sales/daily?start_date=2025-01-14", headers=HB)).json()
        assert d14["total_invoices"] == 0

    async with async_session_factory() as session:
        entry = await session.scalar(select(LedgerEntry).where(LedgerEntry.reference_doc_id == res.json()["id"],
                                                               LedgerEntry.entry_type == "SALES_INVOICE"))
        assert entry.entry_date == date(2025, 1, 15)


# =============================================================================
# 5. Excel / CSV import route
# =============================================================================

CSV_HEADER = ("code,name,tamil_name,category,brand,hsn_code,base_unit,purchase_price,selling_price_retail,"
              "packing_unit,packing_factor,opening_stock_base,is_variable_weight,gst_rate_percent\n")


@pytest.mark.asyncio
async def test_csv_import_route_reports_each_row_and_is_tenant_scoped():
    good, bad = f"IMP-{_uid()}", f"IMPX-{_uid()}"
    csv_text = (CSV_HEADER
                + f"{good},Anchor Switch 6A,,Electricals,Anchor,8536,piece,20,28,Box,20,100,N,18\n"
                + f"{bad},Bad HSN,,Electricals,,85AB,piece,20,28,,,0,N,18\n"
                + f"{good},Duplicate row,,Electricals,,8536,piece,20,28,,,0,N,18\n")
    async with _client() as ac:
        dry = await ac.post("/api/v1/inventory/import?dry_run=true", headers=HB,
                            files={"file": ("catalogue.csv", csv_text.encode("utf-8"), "text/csv")})
        assert dry.status_code == 200, dry.text
        assert dry.json()["committed"] is False
        assert [r["status"] for r in dry.json()["rows"]] == ["VALID", "ERROR", "ERROR"]
        assert all(p["code"] != good for p in (await ac.get("/api/v1/inventory/products", headers=HB)).json())

        res = await ac.post("/api/v1/inventory/import", headers=HB,
                            files={"file": ("catalogue.csv", csv_text.encode("utf-8"), "text/csv")})
        body = res.json()
        assert res.status_code == 200 and body["committed"] is True
        assert (body["total_rows"], body["valid_rows_count"], body["invalid_rows_count"]) == (3, 1, 2)
        assert body["products_created"] == 1
        rows = {r["row_number"]: r for r in body["rows"]}
        assert rows[2]["status"] == "CREATED" and rows[2]["code"] == good
        assert rows[3]["status"] == "ERROR" and rows[3]["errors"][0]["field"] == "hsn_code"
        assert rows[4]["status"] == "ERROR" and "Duplicate code" in rows[4]["errors"][0]["message"]

        b_prod = next(p for p in (await ac.get("/api/v1/inventory/products", headers=HB)).json() if p["code"] == good)
        assert Decimal(b_prod["current_stock_base"]) == Decimal("100.0000")
        assert b_prod["display_stock"] == "5 Box (100 piece)"
        # Tenant A never sees tenant B's import
        assert all(p["code"] != good for p in (await ac.get("/api/v1/inventory/products", headers=HA)).json())


@pytest.mark.asyncio
async def test_xlsx_import_and_file_validation():
    from openpyxl import Workbook

    code = f"XL-{_uid()}"
    wb = Workbook()
    ws = wb.active
    ws.append(CSV_HEADER.strip().split(","))
    ws.append([code, "Cement OPC 53", None, "Cement", "UltraTech", 2523, "kg", 7.5, 8.2, "Bag", 50, 500, "N", 28])
    buf = io.BytesIO()
    wb.save(buf)
    async with _client() as ac:
        res = await ac.post("/api/v1/inventory/import", headers=HB, files={
            "file": ("cement.xlsx", buf.getvalue(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert res.status_code == 200, res.text
        assert res.json()["rows"] == [{"row_number": 2, "code": code, "status": "CREATED", "errors": []}]
        prod = next(p for p in (await ac.get("/api/v1/inventory/products", headers=HB)).json() if p["code"] == code)
        assert prod["hsn_code"] == "2523" and Decimal(prod["gst_rate_percent"]) == Decimal("28.00")
        assert prod["display_stock"] == "10 Bag (500 kg)"

        txt = await ac.post("/api/v1/inventory/import", headers=HB, files={"file": ("x.txt", b"hello", "text/plain")})
        assert txt.status_code == 415
        big = await ac.post("/api/v1/inventory/import", headers=HB,
                            files={"file": ("big.csv", b"a" * (5 * 1024 * 1024 + 1), "text/csv")})
        assert big.status_code == 413
        junk = await ac.post("/api/v1/inventory/import", headers=HB, files={"file": ("bad.xlsx", b"not a zip", "x")})
        assert junk.status_code == 400


# =============================================================================
# 6. Product GST slab
# =============================================================================

@pytest.mark.asyncio
async def test_product_gst_rate_drives_search_invoice_quotation_and_challan():
    async with _client() as ac:
        bad = await ac.post("/api/v1/inventory/products", headers=HA, json={
            "code": f"G7-{_uid()}", "name": "x", "hsn_code": "3208", "base_unit": "piece", "gst_rate_percent": 7})
        assert bad.status_code == 422

        p5 = await _product(ac, HA, gst=5)
        assert Decimal(p5["gst_rate_percent"]) == Decimal("5.00")
        assert Decimal(p5["current_stock_base"]) == Decimal("0.0000")
        default = await _product(ac, HA)
        assert Decimal(default["gst_rate_percent"]) == Decimal("18.00")

        hit = (await ac.get(f"/api/v1/billing/search?q={p5['code']}", headers=HA)).json()[0]
        assert Decimal(hit["gst_rate_percent"]) == Decimal("5.00")

        # Invoice line without gst_rate_percent -> product's 5%: 1000 + 25 + 25 = 1050
        inv = await _invoice(ac, HA, [{"product_id": p5["id"], "unit_name": "piece", "quantity": 10, "unit_price": 100}])
        assert inv.status_code == 201, inv.text
        line = inv.json()["lines"][0]
        assert Decimal(line["gst_rate_percent"]) == Decimal("5.00")
        assert Decimal(line["cgst_amount"]) == Decimal("25.00") and Decimal(line["sgst_amount"]) == Decimal("25.00")
        assert Decimal(inv.json()["grand_total"]) == Decimal("1050.00")
        # An explicit 0% (exempt) is still honoured
        zero = await _invoice(ac, HA, [{"product_id": p5["id"], "unit_name": "piece", "quantity": 1,
                                        "unit_price": 100, "gst_rate_percent": 0}])
        assert Decimal(zero.json()["grand_total"]) == Decimal("100.00")

        q = await ac.post("/api/v1/billing/quotations", headers=HA, json={
            "customer_name": "Quote", "lines": [{"product_id": p5["id"], "unit_name": "piece", "quantity": 2, "unit_price": 50}]})
        assert q.status_code == 201
        assert Decimal(q.json()["lines"][0]["gst_rate_percent"]) == Decimal("5.00")
        assert Decimal(q.json()["total_tax_amount"]) == Decimal("5.00")

        dc = await ac.post("/api/v1/billing/challans", headers=HA, json={
            "customer_name": "Site", "lines": [{"product_id": p5["id"], "unit_name": "piece", "quantity": 4, "unit_price": 250}]})
        assert dc.status_code == 201
        conv = await ac.post(f"/api/v1/billing/challans/{dc.json()['id']}/convert-to-invoice", headers=HA,
                             json={"payment_mode": "CASH"})
        assert conv.status_code == 200, conv.text
        assert Decimal(conv.json()["lines"][0]["gst_rate_percent"]) == Decimal("5.00")
        assert Decimal(conv.json()["grand_total"]) == Decimal("1050.00")  # not 1180 (old hard-coded 18%)


@pytest.mark.asyncio
async def test_product_list_includes_stock_across_godowns():
    async with _client() as ac:
        gid = await _godown_id(ac, HA)
        prod = await _product(ac, HA)
        assert (await _purchase(ac, HA, gid, prod["id"], qty=37, price=10)).status_code == 201
        row = next(p for p in (await ac.get("/api/v1/inventory/products", headers=HA)).json() if p["id"] == prod["id"])
        assert Decimal(row["current_stock_base"]) == Decimal("37.0000")
        assert row["display_stock"] == "3 Box 7 piece (37 piece)"


# =============================================================================
# 7. Party price list code / name
# =============================================================================

@pytest.mark.asyncio
async def test_party_response_carries_price_list_code_and_name():
    async with _client() as ac:
        mason = await _party(ac, HA, price_list_code="CONTRACTOR")
        assert mason["price_list_code"] == "CONTRACTOR" and mason["price_list_name"] == "Contractor / Mason"
        walk_in = await _party(ac, HA)
        assert walk_in["price_list_code"] is None
        listed = next(p for p in (await ac.get("/api/v1/ledger/parties", headers=HA)).json() if p["id"] == mason["id"])
        assert listed["price_list_code"] == "CONTRACTOR"


# =============================================================================
# 8. Cash reconciliation subtracts cash refunds
# =============================================================================

@pytest.mark.asyncio
async def test_cash_reconcile_subtracts_cash_refunds():
    async with _client() as ac:
        prod = await _product(ac, HB)
        line = {"product_id": prod["id"], "unit_name": "piece", "quantity": 1, "unit_price": 1000, "gst_rate_percent": 18}
        # 10:00 IST on 10-Feb-2025
        assert (await _invoice(ac, HB, [line], invoice_date="2025-02-10T04:30:00Z")).status_code == 201
        ret = await ac.post("/api/v1/billing/returns", headers=HB, json={
            "refund_mode": "CASH", "return_date": "2025-02-10T06:30:00Z",
            "lines": [{**line, "unit_price": 200}]})
        assert ret.status_code == 201 and Decimal(ret.json()["grand_total"]) == Decimal("236.00")
        # A credit-note return the same day moves no cash
        await ac.post("/api/v1/billing/returns", headers=HB, json={
            "refund_mode": "CREDIT_NOTE", "return_date": "2025-02-10T06:30:00Z", "lines": [{**line, "unit_price": 50}]})

        rec = await ac.post("/api/v1/reports/cash/reconcile", headers=HB, json={
            "session_date": "2025-02-10", "opening_cash": 500, "actual_cash_counted": 1444})
        assert rec.status_code == 201, rec.text
        body = rec.json()
        assert Decimal(body["cash_sales_amount"]) == Decimal("1180.00")
        assert Decimal(body["cash_refunds_paid"]) == Decimal("236.00")
        assert Decimal(body["expected_cash_drawer"]) == Decimal("1444.00")  # 500 + 1180 - 236
        assert Decimal(body["discrepancy_amount"]) == Decimal("0.00")


# =============================================================================
# 9. Credit notes settle the original invoice
# =============================================================================

@pytest.mark.asyncio
async def test_credit_note_allocated_to_original_invoice_and_excess_becomes_advance():
    async with _client() as ac:
        prod = await _product(ac, HA)
        party = await _party(ac, HA)
        line = {"product_id": prod["id"], "unit_name": "piece", "quantity": 1, "unit_price": 1000, "gst_rate_percent": 18}
        inv = (await _invoice(ac, HA, [line], payment_mode="CREDIT", party_id=party["id"],
                              customer_name=party["name"])).json()
        assert Decimal(inv["due_amount"]) == Decimal("1180.00")

        r1 = await ac.post("/api/v1/billing/returns", headers=HA, json={
            "party_id": party["id"], "customer_name": party["name"], "refund_mode": "CREDIT_NOTE",
            "original_invoice_id": inv["id"], "lines": [{**line, "unit_price": 200}]})
        assert r1.status_code == 201
        snap = await _assert_balance_invariant(DEMO_TENANT_ID, party["id"])
        assert snap == {"unpaid": Decimal("944.00"), "advance": Decimal("0.00"), "balance": Decimal("944.00")}

        # Second credit note (1180) exceeds the remaining 944 due: 236 stays as an advance
        r2 = await ac.post("/api/v1/billing/returns", headers=HA, json={
            "party_id": party["id"], "customer_name": party["name"], "refund_mode": "CREDIT_NOTE",
            "original_invoice_id": inv["id"], "lines": [line]})
        assert r2.status_code == 201
        snap = await _assert_balance_invariant(DEMO_TENANT_ID, party["id"])
        assert snap == {"unpaid": Decimal("0.00"), "advance": Decimal("236.00"), "balance": Decimal("-236.00")}

    async with async_session_factory() as session:
        allocs = (await session.execute(
            select(PaymentAllocation.allocated_amount)
            .join(LedgerEntry, PaymentAllocation.payment_entry_id == LedgerEntry.id)
            .where(LedgerEntry.reference_doc_id.in_([r1.json()["id"], r2.json()["id"]]))
        )).scalars().all()
        assert sorted(allocs) == [Decimal("236.00"), Decimal("944.00")]


# =============================================================================
# 10. Purchase bill number unique per supplier
# =============================================================================

@pytest.mark.asyncio
async def test_purchase_bill_number_unique_per_supplier_not_per_tenant():
    async with _client() as ac:
        gid = await _godown_id(ac, HA)
        prod = await _product(ac, HA)
        s1 = await _party(ac, HA, party_type="SUPPLIER", name=f"Supplier One {_uid()}")
        s2 = await _party(ac, HA, party_type="SUPPLIER", name=f"Supplier Two {_uid()}")
        number = f"INV-{_uid()}"
        a = await _purchase(ac, HA, gid, prod["id"], 1, 10, supplier_id=s1["id"], supplier_name=s1["name"], number=number)
        b = await _purchase(ac, HA, gid, prod["id"], 1, 10, supplier_id=s2["id"], supplier_name=s2["name"], number=number)
        assert a.status_code == 201 and b.status_code == 201
        dup = await _purchase(ac, HA, gid, prod["id"], 1, 10, supplier_id=s1["id"], supplier_name=s1["name"], number=number)
        assert dup.status_code == 400 and "already recorded" in dup.json()["detail"]
        # Another tenant may of course use the same supplier invoice number
        gb = await _godown_id(ac, HB)
        pb = await _product(ac, HB)
        other = await _purchase(ac, HB, gb, pb["id"], 1, 10, supplier_name=s1["name"], number=number)
        assert other.status_code == 201


# =============================================================================
# 11. Supplier dues / ageing are purchase bills reduced by payments
# =============================================================================

@pytest.mark.asyncio
async def test_supplier_dues_are_purchase_bills_settled_fifo_by_payments():
    async with _client() as ac:
        gid = await _godown_id(ac, HA)
        prod = await _product(ac, HA)
        sup = await _party(ac, HA, party_type="SUPPLIER", credit_days=30)
        b1 = await _purchase(ac, HA, gid, prod["id"], 100, 10, supplier_id=sup["id"], supplier_name=sup["name"],
                             bill_date="2026-07-01T06:00:00Z")   # 1000.00
        b2 = await _purchase(ac, HA, gid, prod["id"], 50, 10, supplier_id=sup["id"], supplier_name=sup["name"],
                             bill_date="2026-09-20T06:00:00Z")   # 500.00
        assert b1.status_code == 201 and b2.status_code == 201
        pay = await ac.post("/api/v1/ledger/supplier-payments", headers=HA, json={
            "supplier_id": sup["id"], "amount": 1200, "payment_mode": "CASH", "payment_date": "2026-10-01"})
        assert pay.status_code == 201

        dues = (await ac.get(f"/api/v1/ledger/parties/{sup['id']}/dues?as_of=2026-10-12", headers=HA)).json()
        assert len(dues) == 1  # the 1000 bill is fully paid; the payment itself is not a "bill"
        assert dues[0]["doc_type"] == "PURCHASE_BILL" and dues[0]["doc_number"] == b2.json()["supplier_invoice_number"]
        assert Decimal(dues[0]["total_amount"]) == Decimal("500.00")
        assert Decimal(dues[0]["allocated_amount"]) == Decimal("200.00")
        assert Decimal(dues[0]["due_amount"]) == Decimal("300.00")
        assert dues[0]["age_days"] == 22 and dues[0]["bucket"] == "0-30" and dues[0]["is_overdue"] is False

        ageing = (await ac.get(f"/api/v1/ledger/parties/{sup['id']}/ageing?as_of=2026-10-12", headers=HA)).json()
        assert ageing["side"] == "PAYABLE"
        assert Decimal(ageing["bucket_0_30"]) == Decimal("300.00")
        assert Decimal(ageing["current_balance"]) == Decimal("-300.00")  # we owe 300
        assert Decimal(ageing["unallocated_advance"]) == Decimal("0.00")

        # Customer-side view of the same supplier shows nothing receivable
        recv = (await ac.get(f"/api/v1/ledger/parties/{sup['id']}/dues?side=RECEIVABLE", headers=HA)).json()
        assert recv == []


# =============================================================================
# 12. Reminder call list: overdue only
# =============================================================================

@pytest.mark.asyncio
async def test_call_list_excludes_not_overdue_and_reports_only_overdue_amount():
    async with _client() as ac:
        prod = await _product(ac, HA)
        line = {"product_id": prod["id"], "unit_name": "piece", "quantity": 1, "unit_price": 1000, "gst_rate_percent": 18}
        fresh = await _party(ac, HA, credit_days=30)
        await _invoice(ac, HA, [line], payment_mode="CREDIT", party_id=fresh["id"], customer_name=fresh["name"])

        late = await _party(ac, HA, credit_days=15)
        # 40-day-old bill (overdue by 25 days) + today's bill (not overdue)
        forty_days_ago = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        r1 = await _invoice(ac, HA, [line], payment_mode="CREDIT", party_id=late["id"], customer_name=late["name"],
                            invoice_date=forty_days_ago)
        r2 = await _invoice(ac, HA, [{**line, "unit_price": 500}], payment_mode="CREDIT", party_id=late["id"],
                            customer_name=late["name"])
        assert r1.status_code == 201 and r2.status_code == 201

        calls = (await ac.get("/api/v1/ledger/reminders/call-list", headers=HA)).json()
        ids = {c["party_id"] for c in calls}
        assert fresh["id"] not in ids
        late_row = next(c for c in calls if c["party_id"] == late["id"])
        assert Decimal(late_row["current_balance"]) == Decimal("1770.00")
        assert Decimal(late_row["overdue_amount"]) == Decimal("1180.00")  # not the full 1770 balance
        assert late_row["days_overdue"] == 25
        assert late_row["oldest_bill_number"] == r1.json()["invoice_number"]


# =============================================================================
# 13. Price lists endpoint
# =============================================================================

@pytest.mark.asyncio
async def test_price_lists_endpoint_is_tenant_scoped():
    async with _client() as ac:
        a = (await ac.get("/api/v1/inventory/price-lists", headers=HA)).json()
        assert {p["code"] for p in a} >= {"RETAIL", "CONTRACTOR", "WHOLESALE"}
        assert a[0]["code"] == "RETAIL" and a[0]["is_default"] is True
        assert set(a[0]) == {"id", "code", "name", "is_default"}
        b = (await ac.get("/api/v1/inventory/price-lists", headers=HB)).json()
        assert [(p["code"], p["name"]) for p in b] == [("RETAIL", "B Retail")]
        assert not ({p["id"] for p in a} & {p["id"] for p in b})
