"""Domain logic and operations for Smart Inventory: Purchases, Adjustments, Godowns, Alerts, and Pricing."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.catalogue import Product, ProductUnit, PriceList, ProductPrice
from app.models.stock import (
    Godown,
    StockMovement,
    StockBalance,
    PurchaseBill,
    PurchaseBillLine,
    StockAdjustment,
    StockAdjustmentLine,
)
from app.models.ledger import Party, LedgerEntry
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition
from app.schemas.inventory import (
    GodownCreateSchema,
    GodownTransferCreateSchema,
    GodownTransferResponseSchema,
    GodownStockItemSchema,
    PurchaseBillCreateSchema,
    PurchaseBillResponseSchema,
    StockAdjustmentCreateSchema,
    StockAdjustmentResponseSchema,
    LowStockAlertItemSchema,
    PriceHistoryItemSchema,
    PurchaseCostHistoryItemSchema,
    ProductPriceHistoryResponseSchema,
    UpdateProductPricePayloadSchema,
)

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


def get_product_unit_defs(product: Product) -> List[UnitDefinition]:
    return [
        UnitDefinition(
            unit_name=u.unit_name,
            conversion_factor=u.conversion_factor,
            can_buy=u.can_buy,
            can_sell=u.can_sell,
        )
        for u in product.units
    ]


class InventoryService:

    # -------------------------------------------------------------------------
    # 1. Purchase Bill Processing
    # -------------------------------------------------------------------------
    @staticmethod
    async def process_purchase_bill(
        session: AsyncSession,
        tenant_id: str,
        payload: PurchaseBillCreateSchema,
    ) -> PurchaseBill:
        """Record an inward purchase bill, apportion landed costs, update WAC, and append to stock ledger."""
        # 1. Validate Godown
        godown = await session.scalar(
            select(Godown).where(Godown.id == payload.godown_id, Godown.tenant_id == tenant_id)
        )
        if not godown:
            raise ValueError(f"Godown {payload.godown_id} not found")

        # 2. Check Supplier if provided
        supplier: Optional[Party] = None
        if payload.supplier_id:
            supplier = await session.scalar(
                select(Party).where(Party.id == payload.supplier_id, Party.tenant_id == tenant_id)
            )

        bill_id = str(uuid.uuid4())
        bill_date = payload.bill_date or datetime.now(timezone.utc)

        # 3. Calculate Line-level Subtotals
        calculated_lines = []
        total_taxable = Decimal("0.00")
        total_tax = Decimal("0.00")

        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product)
                .where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
                .options(selectinload(Product.units))
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            base_qty = (line_in.quantity * line_in.conversion_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            gross_amount = (line_in.quantity * line_in.unit_purchase_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            disc = min(line_in.discount_amount, gross_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            taxable = (gross_amount - disc).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            tax = (taxable * (line_in.gst_rate_percent / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            line_tot = (taxable + tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            total_taxable += taxable
            total_tax += tax

            calculated_lines.append({
                "line_number": idx,
                "product": product,
                "product_id": line_in.product_id,
                "unit_name": line_in.unit_name,
                "conversion_factor": line_in.conversion_factor,
                "quantity": line_in.quantity,
                "base_quantity": base_qty,
                "unit_purchase_price": line_in.unit_purchase_price,
                "discount_amount": disc,
                "taxable_amount": taxable,
                "gst_rate_percent": line_in.gst_rate_percent,
                "tax_amount": tax,
                "line_total": line_tot,
            })

        # 4. Apportion Freight, Loading, and Other Expenses across lines
        total_overhead = (payload.freight_charges + payload.loading_charges + payload.other_expenses).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        db_lines: List[PurchaseBillLine] = []
        for line_data in calculated_lines:
            if total_taxable > Decimal("0.00"):
                line_overhead = (total_overhead * (line_data["taxable_amount"] / total_taxable)).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                line_overhead = (total_overhead / Decimal(len(calculated_lines))).quantize(
                    TWO_PLACES, rounding=ROUND_HALF_UP
                )

            # Landed cost per base unit = (taxable_amount + apportioned_overhead) / base_quantity
            total_landed_line = line_data["taxable_amount"] + line_overhead
            if line_data["base_quantity"] > Decimal("0.0000"):
                landed_cost_base = (total_landed_line / line_data["base_quantity"]).quantize(
                    FOUR_PLACES, rounding=ROUND_HALF_UP
                )
            else:
                landed_cost_base = Decimal("0.0000")

            pb_line = PurchaseBillLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                purchase_bill_id=bill_id,
                line_number=line_data["line_number"],
                product_id=line_data["product_id"],
                unit_name=line_data["unit_name"],
                conversion_factor=line_data["conversion_factor"],
                quantity=line_data["quantity"],
                base_quantity=line_data["base_quantity"],
                unit_purchase_price=line_data["unit_purchase_price"],
                discount_amount=line_data["discount_amount"],
                taxable_amount=line_data["taxable_amount"],
                gst_rate_percent=line_data["gst_rate_percent"],
                tax_amount=line_data["tax_amount"],
                line_total=line_data["line_total"],
                apportioned_overhead=line_overhead,
                landed_cost_base=landed_cost_base,
            )
            db_lines.append(pb_line)

        # 5. Grand Total with Round-Off
        exact_bill_total = (total_taxable + total_tax + total_overhead).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        total_invoice_amount = (exact_bill_total + payload.round_off_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        purchase_bill = PurchaseBill(
            id=bill_id,
            tenant_id=tenant_id,
            supplier_id=payload.supplier_id,
            supplier_name=payload.supplier_name,
            supplier_invoice_number=payload.supplier_invoice_number,
            bill_date=bill_date,
            godown_id=payload.godown_id,
            subtotal_taxable=total_taxable,
            total_tax_amount=total_tax,
            freight_charges=payload.freight_charges,
            loading_charges=payload.loading_charges,
            other_expenses=payload.other_expenses,
            round_off_amount=payload.round_off_amount,
            total_invoice_amount=total_invoice_amount,
            notes=payload.notes,
            lines=db_lines,
        )
        session.add(purchase_bill)

        # 6. Append to Stock Movements & Update Stock Balances (Synchronous Ledger Invariant)
        for line_row in db_lines:
            # Append-only Stock Movement
            movement = StockMovement(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                godown_id=payload.godown_id,
                product_id=line_row.product_id,
                movement_type="PURCHASE",
                quantity_base=line_row.base_quantity,
                unit_cost_base=line_row.landed_cost_base,
                reference_doc_type="PURCHASE_BILL",
                reference_doc_id=bill_id,
                reference_doc_number=payload.supplier_invoice_number,
            )
            session.add(movement)

            # Update or create StockBalance cache
            stock_balance = await session.scalar(
                select(StockBalance).where(
                    StockBalance.tenant_id == tenant_id,
                    StockBalance.godown_id == payload.godown_id,
                    StockBalance.product_id == line_row.product_id,
                )
            )
            if stock_balance:
                new_wac = SmartUnitConverter.calculate_weighted_average_cost(
                    current_base_qty=stock_balance.current_quantity_base,
                    current_wac_base=stock_balance.weighted_avg_cost_base,
                    inward_base_qty=line_row.base_quantity,
                    inward_landed_cost_base=line_row.landed_cost_base,
                )
                stock_balance.current_quantity_base += line_row.base_quantity
                stock_balance.weighted_avg_cost_base = new_wac
                stock_balance.last_movement_at = datetime.now(timezone.utc)
            else:
                stock_balance = StockBalance(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    godown_id=payload.godown_id,
                    product_id=line_row.product_id,
                    current_quantity_base=line_row.base_quantity,
                    weighted_avg_cost_base=line_row.landed_cost_base,
                    last_movement_at=datetime.now(timezone.utc),
                )
                session.add(stock_balance)

            # Update Product latest purchase price base
            prod = await session.scalar(select(Product).where(Product.id == line_row.product_id))
            if prod:
                prod.purchase_price_base = line_row.landed_cost_base

        # 7. Post Supplier Ledger Entry if supplier exists
        if supplier:
            ledger_entry = LedgerEntry(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                party_id=supplier.id,
                entry_type="PURCHASE_BILL",
                debit_amount=Decimal("0.00"),
                credit_amount=total_invoice_amount,
                reference_doc_type="PURCHASE_BILL",
                reference_doc_id=bill_id,
                reference_doc_number=payload.supplier_invoice_number,
                entry_date=bill_date.date(),
                notes=f"Purchase bill #{payload.supplier_invoice_number} from {payload.supplier_name}",
            )
            session.add(ledger_entry)
            # For supplier: negative current_balance indicates shop owes supplier money
            supplier.current_balance = (supplier.current_balance - total_invoice_amount).quantize(TWO_PLACES)

        await session.commit()
        await session.refresh(purchase_bill)
        return purchase_bill

    # -------------------------------------------------------------------------
    # 2. Stock Adjustments (Breakage, Theft, Expiry, Physical Count)
    # -------------------------------------------------------------------------
    @staticmethod
    async def process_stock_adjustment(
        session: AsyncSession,
        tenant_id: str,
        payload: StockAdjustmentCreateSchema,
    ) -> StockAdjustment:
        """Record physical inventory count adjustment or loss, writing immutable ledger entries."""
        godown = await session.scalar(
            select(Godown).where(Godown.id == payload.godown_id, Godown.tenant_id == tenant_id)
        )
        if not godown:
            raise ValueError(f"Godown {payload.godown_id} not found")

        adj_id = str(uuid.uuid4())
        adj_date = datetime.now(timezone.utc)
        adj_number = f"ADJ-{adj_date.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

        db_lines: List[StockAdjustmentLine] = []
        total_discrepancy_val = Decimal("0.00")

        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product).where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            # Base quantity difference: quantity * conversion_factor
            base_qty = (line_in.quantity * line_in.conversion_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

            # Current unit cost base from godown balance or product purchase price
            balance = await session.scalar(
                select(StockBalance).where(
                    StockBalance.tenant_id == tenant_id,
                    StockBalance.godown_id == payload.godown_id,
                    StockBalance.product_id == line_in.product_id,
                )
            )
            unit_cost = balance.weighted_avg_cost_base if balance and balance.weighted_avg_cost_base > Decimal("0") else product.purchase_price_base
            discrepancy_val = (abs(base_qty) * unit_cost).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            total_discrepancy_val += discrepancy_val

            adj_line = StockAdjustmentLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                adjustment_id=adj_id,
                line_number=idx,
                product_id=line_in.product_id,
                unit_name=line_in.unit_name,
                conversion_factor=line_in.conversion_factor,
                quantity=line_in.quantity,
                base_quantity=base_qty,
                unit_cost_base=unit_cost,
                discrepancy_value=discrepancy_val,
            )
            db_lines.append(adj_line)

            # Append to Stock Movement
            movement_type = "ADJUSTMENT_IN" if base_qty > Decimal("0.0000") else "ADJUSTMENT_OUT"
            movement = StockMovement(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                godown_id=payload.godown_id,
                product_id=line_in.product_id,
                movement_type=movement_type,
                quantity_base=base_qty,
                unit_cost_base=unit_cost,
                reference_doc_type="STOCK_ADJUSTMENT",
                reference_doc_id=adj_id,
                reference_doc_number=adj_number,
            )
            session.add(movement)

            # Update Stock Balance
            if balance:
                balance.current_quantity_base += base_qty
                balance.last_movement_at = datetime.now(timezone.utc)
            else:
                balance = StockBalance(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    godown_id=payload.godown_id,
                    product_id=line_in.product_id,
                    current_quantity_base=base_qty,
                    weighted_avg_cost_base=unit_cost,
                    last_movement_at=datetime.now(timezone.utc),
                )
                session.add(balance)

        stock_adj = StockAdjustment(
            id=adj_id,
            tenant_id=tenant_id,
            adjustment_number=adj_number,
            adjustment_date=adj_date,
            godown_id=payload.godown_id,
            reason_type=payload.reason_type.upper(),
            total_discrepancy_value=total_discrepancy_val,
            notes=payload.notes,
            lines=db_lines,
        )
        session.add(stock_adj)
        await session.commit()
        await session.refresh(stock_adj)
        return stock_adj

    # -------------------------------------------------------------------------
    # 3. Inter-Godown Stock Transfer
    # -------------------------------------------------------------------------
    @staticmethod
    async def transfer_godown_stock(
        session: AsyncSession,
        tenant_id: str,
        payload: GodownTransferCreateSchema,
    ) -> GodownTransferResponseSchema:
        """Transfer stock between two godowns with paired TRANSFER_OUT and TRANSFER_IN entries."""
        if payload.source_godown_id == payload.target_godown_id:
            raise ValueError("Source and target godowns must be distinct")

        src_godown = await session.scalar(
            select(Godown).where(Godown.id == payload.source_godown_id, Godown.tenant_id == tenant_id)
        )
        if not src_godown:
            raise ValueError("Source godown not found")

        tgt_godown = await session.scalar(
            select(Godown).where(Godown.id == payload.target_godown_id, Godown.tenant_id == tenant_id)
        )
        if not tgt_godown:
            raise ValueError("Target godown not found")

        product = await session.scalar(
            select(Product).where(Product.id == payload.product_id, Product.tenant_id == tenant_id)
        )
        if not product:
            raise ValueError("Product not found")

        base_qty = (payload.quantity * payload.conversion_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        transfer_ref = f"TRF-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"

        # Get Source WAC
        src_balance = await session.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.godown_id == payload.source_godown_id,
                StockBalance.product_id == payload.product_id,
            )
        )
        unit_cost = (
            src_balance.weighted_avg_cost_base
            if src_balance and src_balance.weighted_avg_cost_base > Decimal("0")
            else product.purchase_price_base
        )

        # 1. Source Godown: TRANSFER_OUT
        src_movement = StockMovement(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            godown_id=payload.source_godown_id,
            product_id=payload.product_id,
            movement_type="TRANSFER_OUT",
            quantity_base=-base_qty,
            unit_cost_base=unit_cost,
            reference_doc_type="GODOWN_TRANSFER",
            reference_doc_id=transfer_ref,
            reference_doc_number=transfer_ref,
        )
        session.add(src_movement)

        if src_balance:
            src_balance.current_quantity_base -= base_qty
            src_balance.last_movement_at = datetime.now(timezone.utc)
        else:
            src_balance = StockBalance(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                godown_id=payload.source_godown_id,
                product_id=payload.product_id,
                current_quantity_base=-base_qty,
                weighted_avg_cost_base=unit_cost,
                last_movement_at=datetime.now(timezone.utc),
            )
            session.add(src_balance)

        # 2. Target Godown: TRANSFER_IN
        tgt_movement = StockMovement(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            godown_id=payload.target_godown_id,
            product_id=payload.product_id,
            movement_type="TRANSFER_IN",
            quantity_base=base_qty,
            unit_cost_base=unit_cost,
            reference_doc_type="GODOWN_TRANSFER",
            reference_doc_id=transfer_ref,
            reference_doc_number=transfer_ref,
        )
        session.add(tgt_movement)

        tgt_balance = await session.scalar(
            select(StockBalance).where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.godown_id == payload.target_godown_id,
                StockBalance.product_id == payload.product_id,
            )
        )
        if tgt_balance:
            new_target_wac = SmartUnitConverter.calculate_weighted_average_cost(
                current_base_qty=tgt_balance.current_quantity_base,
                current_wac_base=tgt_balance.weighted_avg_cost_base,
                inward_base_qty=base_qty,
                inward_landed_cost_base=unit_cost,
            )
            tgt_balance.current_quantity_base += base_qty
            tgt_balance.weighted_avg_cost_base = new_target_wac
            tgt_balance.last_movement_at = datetime.now(timezone.utc)
        else:
            tgt_balance = StockBalance(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                godown_id=payload.target_godown_id,
                product_id=payload.product_id,
                current_quantity_base=base_qty,
                weighted_avg_cost_base=unit_cost,
                last_movement_at=datetime.now(timezone.utc),
            )
            session.add(tgt_balance)

        await session.commit()

        return GodownTransferResponseSchema(
            product_id=payload.product_id,
            product_name=product.name,
            source_godown_name=src_godown.name,
            target_godown_name=tgt_godown.name,
            unit_name=payload.unit_name,
            quantity=payload.quantity,
            base_quantity=base_qty,
            unit_cost_base=unit_cost,
            transfer_reference=transfer_ref,
            transferred_at=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # 4. Minimum-Stock Alerts
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_low_stock_alerts(
        session: AsyncSession,
        tenant_id: str,
        godown_id: Optional[str] = None,
    ) -> List[LowStockAlertItemSchema]:
        """Aggregate stock balances across godowns and report low/deficit stock."""
        products_stmt = (
            select(Product)
            .where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .options(selectinload(Product.units))
        )
        products = (await session.execute(products_stmt)).scalars().all()

        alerts: List[LowStockAlertItemSchema] = []

        for p in products:
            # Query sum of current_quantity_base across godowns
            balance_query = select(func.coalesce(func.sum(StockBalance.current_quantity_base), Decimal("0"))).where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.product_id == p.id,
            )
            if godown_id:
                balance_query = balance_query.where(StockBalance.godown_id == godown_id)

            current_stock = (await session.scalar(balance_query)) or Decimal("0")

            if current_stock <= p.min_stock_base:
                deficit = (p.min_stock_base - current_stock).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
                suggested_reorder = max(deficit, p.reorder_quantity_base).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

                # Severity classification
                if current_stock < Decimal("0"):
                    severity = "CRITICAL_NEGATIVE"
                elif current_stock == Decimal("0"):
                    severity = "OUT_OF_STOCK"
                elif current_stock <= (p.min_stock_base * Decimal("0.5")):
                    severity = "CRITICAL_LOW"
                else:
                    severity = "LOW_STOCK"

                unit_defs = get_product_unit_defs(p)
                display_stock = SmartUnitConverter.to_display_units(current_stock, p.base_unit, unit_defs)
                display_reorder = SmartUnitConverter.to_display_units(suggested_reorder, p.base_unit, unit_defs)

                alerts.append(
                    LowStockAlertItemSchema(
                        product_id=p.id,
                        product_code=p.code,
                        product_name=p.name,
                        tamil_name=p.tamil_name,
                        base_unit=p.base_unit,
                        current_stock_base=current_stock,
                        min_stock_base=p.min_stock_base,
                        reorder_quantity_base=p.reorder_quantity_base,
                        deficit_base=deficit,
                        suggested_reorder_base=suggested_reorder,
                        alert_severity=severity,
                        display_stock=display_stock,
                        display_suggested_reorder=display_reorder,
                    )
                )

        # Sort: critical first, then largest deficit
        severity_rank = {"CRITICAL_NEGATIVE": 1, "OUT_OF_STOCK": 2, "CRITICAL_LOW": 3, "LOW_STOCK": 4}
        alerts.sort(key=lambda a: (severity_rank.get(a.alert_severity, 5), -a.deficit_base))
        return alerts

    # -------------------------------------------------------------------------
    # 5. Product Price History & Updates
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_price_history(
        session: AsyncSession,
        tenant_id: str,
        product_id: str,
    ) -> ProductPriceHistoryResponseSchema:
        """Fetch historical selling prices (Retail/Contractor/Wholesale) and purchase cost evolution."""
        product = await session.scalar(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
        if not product:
            raise ValueError("Product not found")

        # 1. Selling Price History
        prices_stmt = (
            select(ProductPrice, PriceList)
            .join(PriceList, ProductPrice.price_list_id == PriceList.id)
            .where(ProductPrice.tenant_id == tenant_id, ProductPrice.product_id == product_id)
            .order_by(ProductPrice.effective_from.desc())
        )
        price_results = (await session.execute(prices_stmt)).all()

        now_utc = datetime.now(timezone.utc)
        selling_history: List[PriceHistoryItemSchema] = []
        for pp, pl in price_results:
            if pp.effective_to is None:
                is_current = True
            else:
                eff_to = pp.effective_to if pp.effective_to.tzinfo else pp.effective_to.replace(tzinfo=timezone.utc)
                is_current = eff_to > now_utc
            selling_history.append(
                PriceHistoryItemSchema(
                    price_list_id=pl.id,
                    price_list_code=pl.code,
                    price_list_name=pl.name,
                    unit_name=pp.unit_name,
                    price=pp.price,
                    min_allowed_price=pp.min_allowed_price,
                    effective_from=pp.effective_from,
                    effective_to=pp.effective_to,
                    is_current=is_current,
                )
            )

        # 2. Purchase Cost History (from Purchase Bill Lines)
        purchases_stmt = (
            select(PurchaseBillLine, PurchaseBill)
            .join(PurchaseBill, PurchaseBillLine.purchase_bill_id == PurchaseBill.id)
            .where(PurchaseBillLine.tenant_id == tenant_id, PurchaseBillLine.product_id == product_id)
            .order_by(PurchaseBill.bill_date.desc())
        )
        purchase_results = (await session.execute(purchases_stmt)).all()

        purchase_history: List[PurchaseCostHistoryItemSchema] = []
        for line, bill in purchase_results:
            purchase_history.append(
                PurchaseCostHistoryItemSchema(
                    purchase_date=bill.bill_date,
                    supplier_name=bill.supplier_name,
                    supplier_invoice_number=bill.supplier_invoice_number,
                    unit_name=line.unit_name,
                    quantity=line.quantity,
                    unit_purchase_price=line.unit_purchase_price,
                    landed_cost_base=line.landed_cost_base,
                )
            )

        return ProductPriceHistoryResponseSchema(
            product_id=product.id,
            product_code=product.code,
            product_name=product.name,
            current_purchase_price_base=product.purchase_price_base,
            selling_price_history=selling_history,
            purchase_cost_history=purchase_history,
        )

    @staticmethod
    async def update_product_price(
        session: AsyncSession,
        tenant_id: str,
        product_id: str,
        payload: UpdateProductPricePayloadSchema,
    ) -> ProductPrice:
        """Update a product's price for a price list, archiving previous price with effective_to timestamp."""
        product = await session.scalar(
            select(Product).where(Product.id == product_id, Product.tenant_id == tenant_id)
        )
        if not product:
            raise ValueError("Product not found")

        price_list = await session.scalar(
            select(PriceList).where(PriceList.id == payload.price_list_id, PriceList.tenant_id == tenant_id)
        )
        if not price_list:
            raise ValueError("Price list not found")

        now_utc = datetime.now(timezone.utc)

        # Expire current active price if any
        current_price = await session.scalar(
            select(ProductPrice).where(
                ProductPrice.tenant_id == tenant_id,
                ProductPrice.product_id == product_id,
                ProductPrice.price_list_id == payload.price_list_id,
                ProductPrice.unit_name == payload.unit_name,
                ProductPrice.effective_to.is_(None),
            )
        )
        if current_price:
            current_price.effective_to = now_utc

        # Insert new price record
        new_price = ProductPrice(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            product_id=product_id,
            unit_name=payload.unit_name,
            price_list_id=payload.price_list_id,
            price=payload.price,
            min_allowed_price=payload.min_allowed_price,
            effective_from=now_utc,
            effective_to=None,
        )
        session.add(new_price)
        await session.commit()
        await session.refresh(new_price)
        return new_price
