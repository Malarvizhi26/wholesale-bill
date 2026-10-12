"""Database initialization and seeding for local dev and testing."""

import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import inspect, select, text
from sqlalchemy.schema import CreateColumn

from app.core.database import Base, engine, async_session_factory
from app.core.rls_policies import TENANT_SETTING, all_rls_statements, tenant_scoped_tables
from app.core.security import hash_pin
from app.models.tenant import Tenant, Device, NumberSeries
from app.models.catalogue import Category, Brand, Product, ProductUnit, PriceList, ProductPrice
from app.models.stock import Godown, StockBalance
from app.models.ledger import Party

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"
# Demo-only owner PIN. The owner MUST change it (POST /api/v1/auth/change-pin) before real use.
DEMO_OWNER_PIN = "1234"


def _add_missing_sqlite_columns(sync_conn) -> None:
    """Local/offline SQLite databases created by an older build: add new nullable/defaulted columns.

    (PostgreSQL deployments are migrated with Alembic instead.)
    """
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in present:
                continue
            if col.primary_key or (not col.nullable and col.server_default is None):
                continue  # cannot add NOT NULL without a default; needs a real migration
            col_def = CreateColumn(col).compile(dialect=sync_conn.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN {col_def}'
            sync_conn.execute(text(ddl))

    # purchase_bills: supplier invoice numbers became unique per (tenant, supplier). SQLite cannot
    # ALTER a constraint, so rebuild the table (alembic batch mode copies the rows across).
    if "purchase_bills" in existing_tables:
        ddl = sync_conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'purchase_bills'")
        ).scalar() or ""
        if "uq_purchase_bill_invoice_number" in ddl:
            from alembic.migration import MigrationContext
            from alembic.operations import Operations

            ops = Operations(MigrationContext.configure(sync_conn))
            with ops.batch_alter_table("purchase_bills", recreate="always") as batch:
                batch.drop_constraint("uq_purchase_bill_invoice_number", type_="unique")
                batch.create_unique_constraint(
                    "uq_purchase_bill_supplier_invoice", ["tenant_id", "supplier_id", "supplier_invoice_number"]
                )


async def init_db() -> None:
    """Create all tables in the active database engine (and RLS policies on PostgreSQL)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "sqlite":
            await conn.run_sync(_add_missing_sqlite_columns)
        elif conn.dialect.name == "postgresql":
            for stmt in all_rls_statements(tenant_scoped_tables(Base.metadata)):
                await conn.execute(text(stmt))


async def seed_demo_data() -> None:
    """Seed initial tenant, price lists, godowns, and sample hardware catalogue."""
    async with async_session_factory() as session:
        if session.bind.dialect.name == "postgresql":
            # FORCE RLS applies to the seeding connection too
            await session.execute(
                text("SELECT set_config(:s, :t, true)"), {"s": TENANT_SETTING, "t": DEMO_TENANT_ID}
            )

        # Check if demo tenant already exists
        result = await session.execute(select(Tenant).where(Tenant.id == DEMO_TENANT_ID))
        existing_tenant = result.scalar_one_or_none()
        if existing_tenant is not None:
            if not existing_tenant.owner_pin_hash:
                # Databases seeded before the owner PIN existed get the demo PIN
                existing_tenant.owner_pin_hash = hash_pin(DEMO_OWNER_PIN)
                await session.commit()
            return  # Already seeded

        # 1. Tenant
        tenant = Tenant(
            id=DEMO_TENANT_ID,
            business_name="Salem Sri Murugan Hardware & Steels",
            trade_name="ஸ்ரீ முருகன் ஹார்ட்வேர்",
            gstin="33AABCS1234F1Z5",
            phone="9876543210",
            email="murugansteel.salem@gmail.com",
            address_line1="142 Junction Main Road",
            city="Salem",
            state_code="33",
            pincode="636004",
            owner_pin_hash=hash_pin(DEMO_OWNER_PIN),
        )
        session.add(tenant)

        # 2. Number Series
        inv_series = NumberSeries(
            tenant_id=DEMO_TENANT_ID,
            doc_type="SALES_INVOICE",
            financial_year="2026-27",
            prefix="C1/26-27/",
            current_number=0,
            range_start=1,
            range_end=999999,
        )
        session.add(inv_series)

        # 3. Godowns
        main_godown = Godown(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="MAIN",
            name="Main Shop Godown",
            is_primary=True,
        )
        bypass_godown = Godown(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="BYPASS",
            name="Salem Bypass Godown 2",
            is_primary=False,
        )
        session.add_all([main_godown, bypass_godown])

        # 4. Price Lists
        retail_pl = PriceList(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="RETAIL",
            name="Retail (Walk-in)",
            is_default=True,
        )
        contractor_pl = PriceList(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="CONTRACTOR",
            name="Contractor / Mason",
            is_default=False,
        )
        wholesale_pl = PriceList(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="WHOLESALE",
            name="Wholesale Dealer",
            is_default=False,
        )
        session.add_all([retail_pl, contractor_pl, wholesale_pl])

        # 5. Categories
        cat_fasteners = Category(id=str(uuid.uuid4()), tenant_id=DEMO_TENANT_ID, name="Fasteners & Screws")
        cat_steel = Category(id=str(uuid.uuid4()), tenant_id=DEMO_TENANT_ID, name="TMT & Structural Steel")
        cat_paints = Category(id=str(uuid.uuid4()), tenant_id=DEMO_TENANT_ID, name="Paints & Primers")
        session.add_all([cat_fasteners, cat_steel, cat_paints])

        # 6. Sample Products
        # Item 1: Screws (Box = 100 pcs)
        prod_screws = Product(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="SCR001",
            name="SS Self-Tapping Screws 25mm",
            tamil_name="எஃகு திருகு 25மிமீ",
            category_id=cat_fasteners.id,
            hsn_code="7318",
            base_unit="piece",
            min_stock_base=Decimal("500"),
            purchase_price_base=Decimal("1.40"),
        )
        session.add(prod_screws)
        unit_box = ProductUnit(
            tenant_id=DEMO_TENANT_ID,
            product_id=prod_screws.id,
            unit_name="Box",
            conversion_factor=Decimal("100"),
            is_default_purchase_unit=True,
            is_default_sales_unit=True,
        )
        unit_pcs = ProductUnit(
            tenant_id=DEMO_TENANT_ID,
            product_id=prod_screws.id,
            unit_name="piece",
            conversion_factor=Decimal("1"),
            is_default_sales_unit=False,
        )
        session.add_all([unit_box, unit_pcs])

        # Item 2: TMT 12mm Rod (variable weight, 1 rod ≈ 10.65 kg)
        prod_tmt = Product(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            code="TMT012",
            name="Tata Tiscon 12mm TMT Bar",
            tamil_name="டாடா டிஸ்கான் 12மிமீ கம்பி",
            category_id=cat_steel.id,
            hsn_code="7214",
            base_unit="kg",
            is_variable_weight=True,
            min_stock_base=Decimal("1000"),
            purchase_price_base=Decimal("58.50"),
        )
        session.add(prod_tmt)
        unit_rod = ProductUnit(
            tenant_id=DEMO_TENANT_ID,
            product_id=prod_tmt.id,
            unit_name="Rod",
            conversion_factor=Decimal("10.65"),
            is_default_sales_unit=True,
        )
        unit_kg = ProductUnit(
            tenant_id=DEMO_TENANT_ID,
            product_id=prod_tmt.id,
            unit_name="kg",
            conversion_factor=Decimal("1"),
            is_default_sales_unit=False,
        )
        session.add_all([unit_rod, unit_kg])

        # 7. Customer Party
        cust_murugan = Party(
            id=str(uuid.uuid4()),
            tenant_id=DEMO_TENANT_ID,
            party_type="CUSTOMER",
            name="Murugan Constructions",
            phone="94433 22110",
            state_code="33",
            price_list_id=contractor_pl.id,
            credit_limit=Decimal("50000.00"),
            credit_days=30,
            opening_balance=Decimal("0.00"),
            current_balance=Decimal("0.00"),
        )
        session.add(cust_murugan)

        await session.commit()
