"""Inventory API endpoints: Products, Units, Purchases, Adjustments, Godowns, Alerts, and Pricing."""

from decimal import Decimal
from typing import List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.rls_session import get_tenant_db_session, get_current_tenant_id
from app.models.catalogue import Product, ProductUnit, ProductPrice
from app.models.stock import Godown, PurchaseBill, StockAdjustment, StockBalance
from app.schemas.product import ProductCreateSchema, ProductResponseSchema
from app.schemas.inventory import (
    GodownCreateSchema,
    GodownResponseSchema,
    GodownTransferCreateSchema,
    GodownTransferResponseSchema,
    GodownStockItemSchema,
    PurchaseBillCreateSchema,
    PurchaseBillResponseSchema,
    StockAdjustmentCreateSchema,
    StockAdjustmentResponseSchema,
    LowStockAlertItemSchema,
    ProductPriceHistoryResponseSchema,
    UpdateProductPricePayloadSchema,
)
from app.modules.inventory.inventory_service import InventoryService, get_product_unit_defs
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition

router = APIRouter(prefix="/inventory", tags=["Inventory"])


# =============================================================================
# 1. Products & Units
# =============================================================================

@router.get("/products", response_model=List[ProductResponseSchema])
async def list_products(
    search: Optional[str] = Query(None, description="Search by name, Tamil name, or code"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List catalogue products for current tenant."""
    tenant_id = get_current_tenant_id()
    query = (
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
        .options(selectinload(Product.units))
    )

    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (Product.name.ilike(search_filter))
            | (Product.tamil_name.ilike(search_filter))
            | (Product.code.ilike(search_filter))
        )

    result = await session.execute(query)
    return result.scalars().all()


@router.post("/products", response_model=ProductResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Create a new product with packaging units."""
    tenant_id = get_current_tenant_id()
    product_id = str(uuid.uuid4())

    product = Product(
        id=product_id,
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        tamil_name=payload.tamil_name,
        category_id=payload.category_id,
        brand_id=payload.brand_id,
        hsn_code=payload.hsn_code,
        base_unit=payload.base_unit,
        is_variable_weight=payload.is_variable_weight,
        min_stock_base=payload.min_stock_base,
        reorder_quantity_base=payload.reorder_quantity_base,
        purchase_price_base=payload.purchase_price_base,
    )
    session.add(product)

    if not payload.units:
        base_unit_obj = ProductUnit(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            product_id=product_id,
            unit_name=payload.base_unit,
            conversion_factor=Decimal("1.0000"),
            can_buy=True,
            can_sell=True,
            is_default_sales_unit=True,
            is_default_purchase_unit=True,
        )
        session.add(base_unit_obj)
    else:
        for u in payload.units:
            unit = ProductUnit(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                product_id=product_id,
                unit_name=u.unit_name,
                conversion_factor=u.conversion_factor,
                can_buy=u.can_buy,
                can_sell=u.can_sell,
                barcode=u.barcode,
                is_default_sales_unit=u.is_default_sales_unit,
                is_default_purchase_unit=u.is_default_purchase_unit,
            )
            session.add(unit)

    if payload.prices:
        for p in payload.prices:
            price_obj = ProductPrice(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                product_id=product_id,
                price_list_id=p.price_list_id,
                unit_name=p.unit_name,
                price=p.price,
                min_allowed_price=p.min_allowed_price,
            )
            session.add(price_obj)

    # Initialize StockBalance in primary godown
    primary_godown = await session.scalar(
        select(Godown).where(Godown.tenant_id == tenant_id, Godown.is_primary.is_(True)).limit(1)
    )
    if not primary_godown:
        primary_godown = await session.scalar(
            select(Godown).where(Godown.tenant_id == tenant_id).limit(1)
        )
    if primary_godown:
        stock_bal = StockBalance(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            godown_id=primary_godown.id,
            product_id=product_id,
            current_quantity_base=Decimal("0.0000"),
            weighted_avg_cost_base=payload.purchase_price_base,
        )
        session.add(stock_bal)

    await session.commit()
    await session.refresh(product)
    return product


@router.get("/products/{product_id}/unit-display")
async def get_mixed_unit_display(
    product_id: str,
    base_qty: Decimal = Query(..., description="Quantity in base units to decompose"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Decompose base quantity into human-readable packaging breakdown (e.g. 963 pcs -> 9 Box 63 pcs)."""
    tenant_id = get_current_tenant_id()
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == tenant_id)
        .options(selectinload(Product.units))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    unit_defs = get_product_unit_defs(product)
    display_str = SmartUnitConverter.to_display_units(
        total_base_qty=base_qty,
        base_unit=product.base_unit,
        packaging_units=unit_defs,
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "base_unit": product.base_unit,
        "base_quantity": base_qty,
        "display": display_str,
    }


# =============================================================================
# 2. Godowns & Transfers
# =============================================================================

@router.get("/godowns", response_model=List[GodownResponseSchema])
async def list_godowns(
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List all storage locations / godowns for the tenant."""
    tenant_id = get_current_tenant_id()
    query = (
        select(Godown)
        .where(Godown.tenant_id == tenant_id, Godown.is_active.is_(True))
        .order_by(Godown.is_primary.desc(), Godown.name)
    )
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/godowns", response_model=GodownResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_godown(
    payload: GodownCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Create a new godown / warehouse."""
    tenant_id = get_current_tenant_id()

    # Check if code already exists
    existing = await session.scalar(
        select(Godown).where(Godown.tenant_id == tenant_id, Godown.code == payload.code)
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Godown code '{payload.code}' already exists")

    if payload.is_primary:
        # unset previous primary
        prev_primaries = (
            await session.execute(
                select(Godown).where(Godown.tenant_id == tenant_id, Godown.is_primary.is_(True))
            )
        ).scalars().all()
        for p in prev_primaries:
            p.is_primary = False

    godown = Godown(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        is_primary=payload.is_primary,
        is_active=True,
    )
    session.add(godown)
    await session.commit()
    await session.refresh(godown)
    return godown


@router.get("/godowns/{godown_id}/stock", response_model=List[GodownStockItemSchema])
async def get_godown_stock(
    godown_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Get real-time stock balances in a specific godown with mixed-unit breakdown."""
    tenant_id = get_current_tenant_id()
    godown = await session.scalar(
        select(Godown).where(Godown.id == godown_id, Godown.tenant_id == tenant_id)
    )
    if not godown:
        raise HTTPException(status_code=404, detail="Godown not found")

    balances = (
        await session.execute(
            select(StockBalance, Product)
            .join(Product, StockBalance.product_id == Product.id)
            .where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.godown_id == godown_id,
                Product.is_active.is_(True),
            )
            .options(selectinload(Product.units))
            .order_by(Product.name)
        )
    ).all()

    stock_items: List[GodownStockItemSchema] = []
    for sb, prod in balances:
        unit_defs = get_product_unit_defs(prod)
        display_str = SmartUnitConverter.to_display_units(
            total_base_qty=sb.current_quantity_base,
            base_unit=prod.base_unit,
            packaging_units=unit_defs,
        )
        is_low = sb.current_quantity_base <= prod.min_stock_base
        stock_items.append(
            GodownStockItemSchema(
                product_id=prod.id,
                product_code=prod.code,
                product_name=prod.name,
                tamil_name=prod.tamil_name,
                base_unit=prod.base_unit,
                current_quantity_base=sb.current_quantity_base,
                weighted_avg_cost_base=sb.weighted_avg_cost_base,
                display_stock=display_str,
                min_stock_base=prod.min_stock_base,
                is_low_stock=is_low,
            )
        )

    return stock_items


@router.post("/godowns/transfer", response_model=GodownTransferResponseSchema)
async def transfer_godown_stock(
    payload: GodownTransferCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Transfer stock between two godowns, appending TRANSFER_OUT and TRANSFER_IN entries."""
    tenant_id = get_current_tenant_id()
    try:
        return await InventoryService.transfer_godown_stock(session, tenant_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 3. Purchase Entries & Landed Cost
# =============================================================================

@router.get("/purchases", response_model=List[PurchaseBillResponseSchema])
async def list_purchases(
    limit: int = Query(50, ge=1, le=200),
    supplier_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List recent purchase bills."""
    tenant_id = get_current_tenant_id()
    query = (
        select(PurchaseBill)
        .where(PurchaseBill.tenant_id == tenant_id)
        .options(selectinload(PurchaseBill.lines))
        .order_by(PurchaseBill.bill_date.desc())
        .limit(limit)
    )
    if supplier_id:
        query = query.where(PurchaseBill.supplier_id == supplier_id)

    result = await session.execute(query)
    return result.scalars().all()


@router.post("/purchases", response_model=PurchaseBillResponseSchema, status_code=status.HTTP_201_CREATED)
async def record_purchase_bill(
    payload: PurchaseBillCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record an inward purchase bill with freight/loading landed cost absorption and WAC update."""
    tenant_id = get_current_tenant_id()
    try:
        return await InventoryService.process_purchase_bill(session, tenant_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/purchases/{purchase_id}", response_model=PurchaseBillResponseSchema)
async def get_purchase_bill(
    purchase_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Retrieve details of a specific purchase bill."""
    tenant_id = get_current_tenant_id()
    purchase = await session.scalar(
        select(PurchaseBill)
        .where(PurchaseBill.id == purchase_id, PurchaseBill.tenant_id == tenant_id)
        .options(selectinload(PurchaseBill.lines))
    )
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase bill not found")
    return purchase


# =============================================================================
# 4. Stock Adjustments (Physical Verification, Breakage, Expiry)
# =============================================================================

@router.get("/adjustments", response_model=List[StockAdjustmentResponseSchema])
async def list_stock_adjustments(
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """List recent physical stock adjustments."""
    tenant_id = get_current_tenant_id()
    query = (
        select(StockAdjustment)
        .where(StockAdjustment.tenant_id == tenant_id)
        .options(selectinload(StockAdjustment.lines))
        .order_by(StockAdjustment.adjustment_date.desc())
        .limit(limit)
    )
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/adjustments", response_model=StockAdjustmentResponseSchema, status_code=status.HTTP_201_CREATED)
async def record_stock_adjustment(
    payload: StockAdjustmentCreateSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Record a stock discrepancy adjustment (breakage, theft, count correction) to the append-only ledger."""
    tenant_id = get_current_tenant_id()
    try:
        return await InventoryService.process_stock_adjustment(session, tenant_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 5. Minimum-Stock Alerts
# =============================================================================

@router.get("/alerts/low-stock", response_model=List[LowStockAlertItemSchema])
async def get_low_stock_alerts(
    godown_id: Optional[str] = Query(None, description="Optional godown filter"),
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Get active minimum-stock and deficit alerts across inventory."""
    tenant_id = get_current_tenant_id()
    return await InventoryService.get_low_stock_alerts(session, tenant_id, godown_id)


# =============================================================================
# 6. Product Price History & Updates
# =============================================================================

@router.get("/products/{product_id}/price-history", response_model=ProductPriceHistoryResponseSchema)
async def get_product_price_history(
    product_id: str,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Get historical selling prices across price lists and purchase costs over time."""
    tenant_id = get_current_tenant_id()
    try:
        return await InventoryService.get_price_history(session, tenant_id, product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/products/{product_id}/prices")
async def update_product_price(
    product_id: str,
    payload: UpdateProductPricePayloadSchema,
    session: AsyncSession = Depends(get_tenant_db_session),
):
    """Update a product's price for a price list, archiving the prior price in history."""
    tenant_id = get_current_tenant_id()
    try:
        new_price = await InventoryService.update_product_price(session, tenant_id, product_id, payload)
        return {
            "status": "success",
            "message": "Price updated successfully with history preserved",
            "price_id": new_price.id,
            "effective_from": new_price.effective_from,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
