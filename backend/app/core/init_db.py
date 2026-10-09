"""Database initialization and seeding for local dev and testing."""

import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import Base, engine, async_session_factory
from app.models.tenant import Tenant, Device, NumberSeries
from app.models.catalogue import Category, Brand, Product, ProductUnit, PriceList, ProductPrice
from app.models.stock import Godown, StockBalance
from app.models.ledger import Party

DEMO_TENANT_ID = "00000000-0000-0000-0000-000000000001"


async def init_db() -> None:
    """Create all tables in the active database engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_demo_data() -> None:
    """Seed initial tenant, price lists, godowns, and sample hardware catalogue."""
    async with async_session_factory() as session:
        # Check if demo tenant already exists
        result = await session.execute(select(Tenant).where(Tenant.id == DEMO_TENANT_ID))
        if result.scalar_one_or_none() is not None:
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
