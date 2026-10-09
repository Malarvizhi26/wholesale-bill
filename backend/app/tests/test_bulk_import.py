"""Tests for Excel/CSV Bulk Import Engine."""

import pytest
import pytest_asyncio
from decimal import Decimal
from sqlalchemy import select
from app.core.database import async_session_factory
from app.core.init_db import init_db, seed_demo_data, DEMO_TENANT_ID
from app.modules.inventory.excel_import import CatalogueImportEngine
from app.models.catalogue import Product, ProductUnit
from app.models.stock import StockBalance

SAMPLE_CSV = """code,name,tamil_name,category,brand,hsn_code,base_unit,purchase_price,selling_price_retail,selling_price_contractor,packing_unit,packing_factor,opening_stock_base,is_variable_weight
ROD016,16mm TMT Rod Fe500,16மிமீ கம்பி,TMT Steel,Jindal,7214,kg,56.00,64.00,61.50,Rod,18.96,1896.00,Y
WIRE90,Finolex 1.5 sqmm Wire,கம்பி வயர்,Electricals,Finolex,8544,metre,14.50,18.00,16.50,Coil,90.00,450.00,N
"""

INVALID_CSV = """code,name,tamil_name,category,brand,hsn_code,base_unit,purchase_price,selling_price_retail,selling_price_contractor,packing_unit,packing_factor,opening_stock_base,is_variable_weight
,Missing Code Item,,Fasteners,,7318,piece,10,15,,,1,,N
BAD001,Bad HSN Item,,Fasteners,,ABC,piece,10,15,,,1,,N
BAD002,Bad Base Unit Item,,Fasteners,,7318,unknown_unit,10,15,,,1,,N
"""


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()
    await seed_demo_data()


def test_parse_valid_csv():
    rows, errors = CatalogueImportEngine.parse_csv_stream(SAMPLE_CSV)
    assert len(errors) == 0
    assert len(rows) == 2

    # Check 16mm TMT rod
    rod = rows[0]
    assert rod.code == "ROD016"
    assert rod.is_variable_weight is True
    assert rod.packing_unit == "Rod"
    assert rod.packing_factor == Decimal("18.96")

    # Check Wire
    wire = rows[1]
    assert wire.code == "WIRE90"
    assert wire.packing_unit == "Coil"
    assert wire.packing_factor == Decimal("90.00")


def test_parse_invalid_csv_detects_errors():
    rows, errors = CatalogueImportEngine.parse_csv_stream(INVALID_CSV)
    assert len(rows) == 0
    assert len(errors) == 3

    fields = [e.field for e in errors]
    assert "code" in fields
    assert "hsn_code" in fields
    assert "base_unit" in fields


@pytest.mark.asyncio
async def test_commit_catalogue_creates_db_records():
    import uuid
    test_tenant_id = str(uuid.uuid4())

    rows, errors = CatalogueImportEngine.parse_csv_stream(SAMPLE_CSV)
    assert len(errors) == 0

    async with async_session_factory() as session:
        result = await CatalogueImportEngine.commit_catalogue(
            tenant_id=test_tenant_id,
            rows=rows,
            session=session,
        )
        assert result["status"] == "success"
        assert result["products_created"] == 2
        assert result["units_created"] >= 4

        # Verify product exists in DB
        prod_res = await session.execute(
            select(Product).where(Product.tenant_id == test_tenant_id, Product.code == "ROD016")
        )
        prod = prod_res.scalar_one_or_none()
        assert prod is not None
        assert prod.name == "16mm TMT Rod Fe500"
        assert prod.is_variable_weight is True

        # Verify opening stock balance exists
        stock_res = await session.execute(
            select(StockBalance).where(StockBalance.tenant_id == test_tenant_id, StockBalance.product_id == prod.id)
        )
        stock = stock_res.scalar_one_or_none()
        assert stock is not None
        assert stock.current_quantity_base == Decimal("1896.0000")
