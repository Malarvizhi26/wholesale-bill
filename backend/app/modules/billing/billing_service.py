"""Billing Service: Domain engine for Fast POS, Invoices, Returns, Quotations, and Delivery Challans."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.tenant import Tenant, NumberSeries
from app.models.catalogue import Product, ProductUnit, PriceList, ProductPrice
from app.core.timeutils import ist_date_of, to_utc
from app.models.stock import Godown, StockMovement, StockBalance, StockAlert
from app.models.ledger import Party, LedgerEntry, PaymentAllocation
from app.models.billing import (
    SalesInvoice,
    SalesInvoiceLine,
    SalesReturn,
    SalesReturnLine,
    Quotation,
    QuotationLine,
    DeliveryChallan,
    DeliveryChallanLine,
)
from app.modules.inventory.unit_converter import SmartUnitConverter, UnitDefinition
from app.modules.billing.thermal_printer import ThermalReceiptGenerator
from app.schemas.billing import (
    ProductSearchItemSchema,
    ProductUnitInfo,
    SalesInvoiceCreateSchema,
    SalesReturnCreateSchema,
    QuotationCreateSchema,
    DeliveryChallanCreateSchema,
    UnitDecomposeRequestSchema,
    UnitDecomposeResponseSchema,
)

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class BillingService:

    # -------------------------------------------------------------------------
    # 0. Document Number Generation
    # -------------------------------------------------------------------------
    @staticmethod
    async def get_next_number(
        session: AsyncSession,
        tenant_id: str,
        doc_type: str,
        default_prefix: str,
        financial_year: str = "2026-27",
    ) -> str:
        """Fetch next sequential document number from NumberSeries or initialize."""
        stmt = select(NumberSeries).where(
            NumberSeries.tenant_id == tenant_id,
            NumberSeries.doc_type == doc_type,
            NumberSeries.financial_year == financial_year,
        )
        res = await session.execute(stmt)
        series = res.scalar_one_or_none()

        if not series:
            series = NumberSeries(
                tenant_id=tenant_id,
                doc_type=doc_type,
                financial_year=financial_year,
                prefix=default_prefix,
                current_number=1,
                range_start=1,
                range_end=999999,
            )
            session.add(series)
            num = 1
        else:
            series.current_number += 1
            num = series.current_number

        # Offline counters sync invoices numbered from the same series; skip numbers already taken
        if doc_type == "SALES_INVOICE":
            while await session.scalar(
                select(SalesInvoice.id).where(
                    SalesInvoice.tenant_id == tenant_id,
                    SalesInvoice.invoice_number == f"{series.prefix}{num:04d}",
                )
            ):
                series.current_number = num + 1
                num = series.current_number

        return f"{series.prefix}{num:04d}"

    # -------------------------------------------------------------------------
    # 1. Product & Barcode Search
    # -------------------------------------------------------------------------
    @staticmethod
    async def search_products_and_barcodes(
        session: AsyncSession,
        tenant_id: str,
        query: str,
        godown_id: Optional[str] = None,
        price_list_id: Optional[str] = None,
        limit: int = 25,
    ) -> List[ProductSearchItemSchema]:
        """Search products by exact barcode, product code, product name, or Tamil name.
        
        If a barcode matches a specific packaging unit, matched_unit is automatically set.
        """
        clean_q = query.strip()
        if not clean_q:
            return []

        # Find Primary Godown if not supplied
        if not godown_id:
            primary_godown = await session.scalar(
                select(Godown).where(
                    Godown.tenant_id == tenant_id,
                    Godown.is_primary == True,
                    Godown.is_active == True,
                )
            )
            if primary_godown:
                godown_id = primary_godown.id

        # Find Default Price List if not supplied
        if not price_list_id:
            default_pl = await session.scalar(
                select(PriceList).where(
                    PriceList.tenant_id == tenant_id,
                    PriceList.is_default == True,
                )
            )
            if default_pl:
                price_list_id = default_pl.id

        # Query products matching code, name, tamil_name, or unit barcode
        # 1. First check if any unit barcode has exact or partial match
        barcode_unit_stmt = (
            select(ProductUnit)
            .where(
                ProductUnit.tenant_id == tenant_id,
                ProductUnit.barcode.ilike(f"%{clean_q}%"),
            )
        )
        barcode_units = (await session.execute(barcode_unit_stmt)).scalars().all()
        matched_barcode_prod_ids = {u.product_id: u.unit_name for u in barcode_units}

        # 2. Main product query
        stmt = (
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.is_active == True,
                or_(
                    Product.code.ilike(f"%{clean_q}%"),
                    Product.name.ilike(f"%{clean_q}%"),
                    Product.tamil_name.ilike(f"%{clean_q}%"),
                    Product.id.in_(matched_barcode_prod_ids.keys()) if matched_barcode_prod_ids else False,
                ),
            )
            .options(
                selectinload(Product.units),
                selectinload(Product.prices),
            )
            .limit(limit)
        )
        products = (await session.execute(stmt)).scalars().all()

        results: List[ProductSearchItemSchema] = []
        for p in products:
            # Determine matched unit
            matched_unit_name: Optional[str] = matched_barcode_prod_ids.get(p.id)
            if not matched_unit_name:
                default_unit = next((u for u in p.units if u.is_default_sales_unit), None)
                matched_unit_name = default_unit.unit_name if default_unit else (p.units[0].unit_name if p.units else p.base_unit)

            # Get Godown stock
            stock_qty = Decimal("0.0000")
            if godown_id:
                sb = await session.scalar(
                    select(StockBalance).where(
                        StockBalance.tenant_id == tenant_id,
                        StockBalance.godown_id == godown_id,
                        StockBalance.product_id == p.id,
                    )
                )
                if sb:
                    stock_qty = sb.current_quantity_base

            # Format stock display
            unit_defs = [
                UnitDefinition(
                    unit_name=u.unit_name,
                    conversion_factor=u.conversion_factor,
                    can_buy=u.can_buy,
                    can_sell=u.can_sell,
                    barcode=u.barcode,
                    is_default_sales_unit=u.is_default_sales_unit,
                )
                for u in p.units
            ]
            stock_display = SmartUnitConverter.to_display_units(stock_qty, p.base_unit, unit_defs)

            # Price map for current price list
            price_map: Dict[str, Decimal] = {}
            for pr in p.prices:
                # Only the current (non-archived) price row counts; archived rows keep price history
                if price_list_id and pr.price_list_id == price_list_id and pr.effective_to is None:
                    price_map[pr.unit_name] = pr.price

            # Build unit info list
            unit_infos: List[ProductUnitInfo] = []
            matched_selling_price = Decimal("0.00")
            for u in p.units:
                # Fallback price calculation if price list has no entry
                price = price_map.get(u.unit_name)
                if price is None:
                    # Estimate price from purchase_price_base * conversion_factor * 1.15
                    price = (p.purchase_price_base * u.conversion_factor * Decimal("1.15")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

                if u.unit_name == matched_unit_name:
                    matched_selling_price = price

                unit_infos.append(
                    ProductUnitInfo(
                        unit_name=u.unit_name,
                        conversion_factor=u.conversion_factor,
                        can_sell=u.can_sell,
                        barcode=u.barcode,
                        is_default_sales_unit=u.is_default_sales_unit,
                        selling_price=price,
                    )
                )

            # GST slab comes from the product master (0/5/12/18/28)
            gst_rate = p.gst_rate_percent if p.gst_rate_percent is not None else Decimal("18.00")

            results.append(
                ProductSearchItemSchema(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    tamil_name=p.tamil_name,
                    hsn_code=p.hsn_code,
                    base_unit=p.base_unit,
                    is_variable_weight=p.is_variable_weight,
                    gst_rate_percent=gst_rate,
                    current_stock_base=stock_qty,
                    current_stock_display=stock_display,
                    cost_price_base=p.purchase_price_base,
                    matched_unit=matched_unit_name,
                    selling_price=matched_selling_price,
                    units=unit_infos,
                )
            )

        return results

    # -------------------------------------------------------------------------
    # 2. Unit Decomposition Helper
    # -------------------------------------------------------------------------
    @staticmethod
    async def decompose_unit_quantity(
        session: AsyncSession,
        tenant_id: str,
        payload: UnitDecomposeRequestSchema,
    ) -> UnitDecomposeResponseSchema:
        """Decompose entered unit quantity into base units and hierarchical representation."""
        product = await session.scalar(
            select(Product)
            .where(Product.id == payload.product_id, Product.tenant_id == tenant_id)
            .options(selectinload(Product.units))
        )
        if not product:
            raise ValueError(f"Product {payload.product_id} not found")

        unit = next((u for u in product.units if u.unit_name.lower() == payload.unit_name.lower()), None)
        factor = unit.conversion_factor if unit else Decimal("1.0")

        u_def = UnitDefinition(
            unit_name=payload.unit_name,
            conversion_factor=factor,
        )
        base_qty = SmartUnitConverter.to_base_quantity(
            quantity=payload.quantity,
            unit=u_def,
            is_variable_weight=product.is_variable_weight,
            actual_weight_kg=payload.actual_weight_kg,
        )

        all_unit_defs = [
            UnitDefinition(
                unit_name=u.unit_name,
                conversion_factor=u.conversion_factor,
                can_buy=u.can_buy,
                can_sell=u.can_sell,
            )
            for u in product.units
        ]
        display = SmartUnitConverter.to_display_units(base_qty, product.base_unit, all_unit_defs)

        return UnitDecomposeResponseSchema(
            product_id=product.id,
            base_quantity=base_qty,
            base_unit=product.base_unit,
            display_units=display,
        )

    # -------------------------------------------------------------------------
    # 3. Post Sales Invoice (GST Invoice)
    # -------------------------------------------------------------------------
    @staticmethod
    async def create_sales_invoice(
        session: AsyncSession,
        tenant_id: str,
        payload: SalesInvoiceCreateSchema,
    ) -> SalesInvoice:
        """Calculate GST, write SalesInvoice + Lines, update StockMovements & Balances, and write Ledger."""
        # 0. Idempotent offline sync: a re-sent offline invoice returns the already-posted copy.
        if payload.invoice_number:
            existing = await session.scalar(
                select(SalesInvoice)
                .where(
                    SalesInvoice.tenant_id == tenant_id,
                    SalesInvoice.invoice_number == payload.invoice_number,
                )
                .options(selectinload(SalesInvoice.lines))
            )
            if existing:
                if payload.is_offline_created:
                    return existing
                raise ValueError(f"Invoice number {payload.invoice_number} already exists")

        # 1. Fetch Tenant profile for state and shop details
        tenant = await session.scalar(select(Tenant).where(Tenant.id == tenant_id))
        tenant_state = tenant.state_code if tenant else "33"
        is_inter_state = tenant_state != payload.place_of_supply_state_code

        party: Optional[Party] = None
        if payload.party_id:
            party = await session.scalar(
                select(Party).where(Party.id == payload.party_id, Party.tenant_id == tenant_id)
            )
        review_flags: List[str] = []
        # Detailed rows persisted to stock_alerts for the owner review queue
        alert_rows: List[Dict[str, Any]] = []

        # 2. Resolve Godown
        godown_id = payload.godown_id
        if not godown_id:
            primary_godown = await session.scalar(
                select(Godown).where(
                    Godown.tenant_id == tenant_id,
                    Godown.is_primary == True,
                    Godown.is_active == True,
                )
            )
            if not primary_godown:
                raise ValueError("No active godown found for tenant")
            godown_id = primary_godown.id

        # 3. Resolve Price List (explicit > party's tier (Contractor/Wholesale) > default Retail)
        price_list_id = payload.price_list_id
        if not price_list_id and party and party.price_list_id:
            price_list_id = party.price_list_id
        if not price_list_id:
            default_pl = await session.scalar(
                select(PriceList).where(
                    PriceList.tenant_id == tenant_id,
                    PriceList.is_default == True,
                )
            )
            if not default_pl:
                # Any active pricelist
                any_pl = await session.scalar(select(PriceList).where(PriceList.tenant_id == tenant_id))
                if not any_pl:
                    raise ValueError("No price list configured for tenant")
                price_list_id = any_pl.id
            else:
                price_list_id = default_pl.id

        # 4. Generate Invoice Number if not provided
        invoice_number = payload.invoice_number
        if not invoice_number:
            invoice_number = await BillingService.get_next_number(
                session=session,
                tenant_id=tenant_id,
                doc_type="SALES_INVOICE",
                default_prefix="C1/26-27/",
            )

        invoice_id = str(uuid.uuid4())
        # Stored in UTC; business dates (ledger entry_date, reports) are derived in IST
        invoice_date = to_utc(payload.invoice_date) or datetime.now(timezone.utc)

        # 5. Calculate Lines
        invoice_lines: List[SalesInvoiceLine] = []
        subtotal_taxable = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_cgst = Decimal("0.00")
        total_sgst = Decimal("0.00")
        total_igst = Decimal("0.00")

        # Cache products and stock balances
        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product)
                .where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
                .options(selectinload(Product.units))
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            # Catalogue conversion factor is authoritative (stock must move in base units)
            conv_factor = SmartUnitConverter.resolve_conversion_factor(
                product.units, line_in.unit_name, line_in.conversion_factor
            )

            # Calculate base quantity (variable-weight items move by actual weighed kg)
            is_var_weight = line_in.is_variable_weight or product.is_variable_weight
            if is_var_weight and line_in.actual_weight_kg is not None:
                base_qty = line_in.actual_weight_kg.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            else:
                base_qty = (line_in.quantity * conv_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)

            # Floor price protection for the applied price list (Retail / Wholesale / Contractor)
            floor_price = await session.scalar(
                select(ProductPrice.min_allowed_price).where(
                    ProductPrice.tenant_id == tenant_id,
                    ProductPrice.product_id == product.id,
                    ProductPrice.price_list_id == price_list_id,
                    func.lower(ProductPrice.unit_name) == line_in.unit_name.strip().lower(),
                    ProductPrice.effective_to.is_(None),
                )
            )
            if floor_price is not None and line_in.unit_price < floor_price:
                if payload.is_offline_created or payload.owner_override:
                    if "BELOW_FLOOR_PRICE" not in review_flags:
                        review_flags.append("BELOW_FLOOR_PRICE")
                    alert_rows.append({
                        "alert_type": "BELOW_FLOOR_PRICE",
                        "product_id": product.id,
                        "message": (
                            f"Line {idx}: {product.code}/{line_in.unit_name} sold at {line_in.unit_price} "
                            f"below floor price {floor_price}"
                        ),
                    })
                else:
                    raise ValueError(
                        f"Price {line_in.unit_price} for {product.code}/{line_in.unit_name} is below the "
                        f"floor price {floor_price}. Owner override required."
                    )

            # Cost at sale = current godown Weighted Average Cost (fallback: last landed cost)
            cost_sb = await session.scalar(
                select(StockBalance).where(
                    StockBalance.tenant_id == tenant_id,
                    StockBalance.godown_id == godown_id,
                    StockBalance.product_id == product.id,
                )
            )
            cost_at_sale = (
                cost_sb.weighted_avg_cost_base
                if cost_sb and cost_sb.weighted_avg_cost_base > Decimal("0")
                else product.purchase_price_base
            )

            # Gross & Discount
            gross = (line_in.quantity * line_in.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            if line_in.discount_type == "PERCENT":
                disc = (gross * (line_in.discount_value / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                disc = line_in.discount_value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            disc = min(disc, gross)
            taxable = gross - disc

            # GST rate: an explicit rate (incl. 0% / exempt) is honoured; a missing rate uses the product's slab
            gst_rate = line_in.gst_rate_percent if line_in.gst_rate_percent is not None else product.gst_rate_percent
            hsn = line_in.hsn_code or product.hsn_code

            if is_inter_state:
                cgst_pct = Decimal("0.00")
                sgst_pct = Decimal("0.00")
                igst_pct = gst_rate

                cgst_amt = Decimal("0.00")
                sgst_amt = Decimal("0.00")
                igst_amt = (taxable * (igst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            else:
                half_rate = gst_rate / Decimal("2")
                cgst_pct = half_rate
                sgst_pct = half_rate
                igst_pct = Decimal("0.00")

                cgst_amt = (taxable * (cgst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                sgst_amt = (taxable * (sgst_pct / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                igst_amt = Decimal("0.00")

            line_tot = taxable + cgst_amt + sgst_amt + igst_amt

            subtotal_taxable += taxable
            total_discount += disc
            total_cgst += cgst_amt
            total_sgst += sgst_amt
            total_igst += igst_amt

            line_obj = SalesInvoiceLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                line_number=idx,
                product_id=product.id,
                unit_name=line_in.unit_name,
                conversion_factor=conv_factor,
                quantity=line_in.quantity,
                actual_weight_kg=line_in.actual_weight_kg,
                base_quantity=base_qty,
                unit_price=line_in.unit_price,
                cost_price_base_at_sale=cost_at_sale,
                discount_type=line_in.discount_type,
                discount_value=line_in.discount_value,
                discount_amount=disc,
                taxable_amount=taxable,
                hsn_code=hsn,
                gst_rate_percent=gst_rate,
                cgst_percent=cgst_pct,
                cgst_amount=cgst_amt,
                sgst_percent=sgst_pct,
                sgst_amount=sgst_amt,
                igst_percent=igst_pct,
                igst_amount=igst_amt,
                line_total=line_tot,
            )
            invoice_lines.append(line_obj)

        total_tax = total_cgst + total_sgst + total_igst
        exact_total = subtotal_taxable + total_tax
        grand_total = exact_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(TWO_PLACES)
        round_off = (grand_total - exact_total).quantize(TWO_PLACES)

        # Paid & Due
        if payload.paid_amount is not None:
            paid = max(Decimal("0.00"), min(payload.paid_amount, grand_total)).quantize(TWO_PLACES)
        elif payload.payment_mode in ("CASH", "UPI", "CARD"):
            paid = grand_total
        else:  # CREDIT
            paid = Decimal("0.00")
        due = (grand_total - paid).quantize(TWO_PLACES)

        # Credit limit check on the credit (unpaid) portion of this bill
        if party and due > Decimal("0.00") and party.credit_limit > Decimal("0.00"):
            projected_balance = party.current_balance + due
            if projected_balance > party.credit_limit:
                if payload.is_offline_created or payload.owner_override:
                    review_flags.append("CREDIT_LIMIT_EXCEEDED")
                    alert_rows.append({
                        "alert_type": "CREDIT_LIMIT_EXCEEDED",
                        "message": (
                            f"{party.name}: projected balance {projected_balance} exceeds credit limit "
                            f"{party.credit_limit}"
                        ),
                    })
                else:
                    raise ValueError(
                        f"Credit limit exceeded for {party.name}: projected balance {projected_balance} "
                        f"> limit {party.credit_limit}. Owner override required."
                    )

        # Dynamic UPI QR
        shop_vpa = "store@icici"
        shop_name = tenant.business_name if tenant else "Hardware Store"
        upi_qr = ThermalReceiptGenerator.generate_upi_qr_string(
            vpa=shop_vpa,
            payee_name=shop_name,
            amount=grand_total,
            invoice_number=invoice_number,
        )

        invoice = SalesInvoice(
            id=invoice_id,
            tenant_id=tenant_id,
            device_id=payload.device_id,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            party_id=payload.party_id,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            customer_gstin=payload.customer_gstin,
            place_of_supply_state_code=payload.place_of_supply_state_code,
            is_b2b=payload.is_b2b,
            price_list_id=price_list_id,
            godown_id=godown_id,
            status="POSTED",
            subtotal_amount=subtotal_taxable,
            discount_amount=total_discount,
            cgst_amount=total_cgst,
            sgst_amount=total_sgst,
            igst_amount=total_igst,
            total_tax_amount=total_tax,
            round_off_amount=round_off,
            grand_total=grand_total,
            paid_amount=paid,
            due_amount=due,
            payment_mode=payload.payment_mode,
            payment_breakdown=payload.payment_breakdown,
            upi_qr_string=upi_qr,
            is_offline_created=payload.is_offline_created,
            offline_created_at=payload.offline_created_at,
            synced_at=datetime.now(timezone.utc) if payload.is_offline_created else None,
            lines=invoice_lines,
        )
        session.add(invoice)

        # 6. Physical Stock Movement
        # If this invoice is converted from a Delivery Challan, stock was ALREADY deducted upon dispatch!
        if not payload.delivery_challan_id:
            for line in invoice_lines:
                # Append Stock Movement
                sm = StockMovement(
                    tenant_id=tenant_id,
                    godown_id=godown_id,
                    product_id=line.product_id,
                    movement_type="SALE",
                    quantity_base=-line.base_quantity,
                    unit_cost_base=line.cost_price_base_at_sale,
                    reference_doc_type="SALES_INVOICE",
                    reference_doc_id=invoice.id,
                    reference_doc_number=invoice.invoice_number,
                )
                session.add(sm)

                # Update Stock Balance
                sb = await session.scalar(
                    select(StockBalance).where(
                        StockBalance.tenant_id == tenant_id,
                        StockBalance.godown_id == godown_id,
                        StockBalance.product_id == line.product_id,
                    )
                )
                if not sb:
                    sb = StockBalance(
                        tenant_id=tenant_id,
                        godown_id=godown_id,
                        product_id=line.product_id,
                        current_quantity_base=-line.base_quantity,
                        weighted_avg_cost_base=line.cost_price_base_at_sale,
                        last_movement_at=invoice_date,
                    )
                    session.add(sb)
                    await session.flush()  # make the new balance visible to later lines (autoflush is off)
                else:
                    sb.current_quantity_base -= line.base_quantity
                    sb.last_movement_at = invoice_date

                # Negative stock is allowed on POS sales but flagged for owner review
                if sb.current_quantity_base < Decimal("0"):
                    if "NEGATIVE_STOCK_WARNING" not in review_flags:
                        review_flags.append("NEGATIVE_STOCK_WARNING")
                    # One alert per product (keep the latest, most negative balance)
                    alert_rows = [
                        a for a in alert_rows
                        if not (a["alert_type"] == "NEGATIVE_STOCK_WARNING" and a.get("product_id") == line.product_id)
                    ]
                    alert_rows.append({
                        "alert_type": "NEGATIVE_STOCK_WARNING",
                        "product_id": line.product_id,
                        "message": f"Stock went negative: balance {sb.current_quantity_base} base units after this bill",
                    })
        else:
            # Mark delivery challan as INVOICED
            dc = await session.scalar(
                select(DeliveryChallan).where(
                    DeliveryChallan.id == payload.delivery_challan_id,
                    DeliveryChallan.tenant_id == tenant_id,
                )
            )
            if dc:
                dc.status = "INVOICED"
                dc.invoiced_invoice_id = invoice.id

        # 7. Customer Ledger Entry
        if party:
            # Debit customer account for the invoice grand total
            le_inv = LedgerEntry(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                party_id=party.id,
                entry_type="SALES_INVOICE",
                debit_amount=grand_total,
                credit_amount=Decimal("0.00"),
                reference_doc_type="SALES_INVOICE",
                reference_doc_id=invoice.id,
                reference_doc_number=invoice.invoice_number,
                entry_date=ist_date_of(invoice_date),
                notes=f"Sales Invoice {invoice.invoice_number}",
            )
            session.add(le_inv)

            # If counter payment was received, add immediate Payment Receipt credit entry
            if paid > Decimal("0.00"):
                le_pay = LedgerEntry(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    party_id=party.id,
                    entry_type="PAYMENT_RECEIPT",
                    debit_amount=Decimal("0.00"),
                    credit_amount=paid,
                    reference_doc_type="SALES_INVOICE",
                    reference_doc_id=invoice.id,
                    reference_doc_number=invoice.invoice_number,
                    entry_date=ist_date_of(invoice_date),
                    notes=f"Payment for {invoice.invoice_number} via {payload.payment_mode}",
                )
                session.add(le_pay)
                # Settle the counter payment against this very bill so it never shows as an open due
                session.add(
                    PaymentAllocation(
                        id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        payment_entry_id=le_pay.id,
                        invoice_entry_id=le_inv.id,
                        allocated_amount=paid,
                    )
                )

            # Update party balance: balance increases by net due
            party.current_balance += due

        # 8. Persist owner review flags (accepted conflicts are never silently lost)
        for alert in alert_rows:
            session.add(
                StockAlert(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    alert_type=alert["alert_type"],
                    status="OPEN",
                    reference_doc_type="SALES_INVOICE",
                    reference_doc_id=invoice.id,
                    reference_doc_number=invoice.invoice_number,
                    product_id=alert.get("product_id"),
                    party_id=party.id if party else None,
                    godown_id=godown_id,
                    message=alert["message"],
                    is_offline_created=payload.is_offline_created,
                    owner_override=payload.owner_override,
                )
            )

        await session.commit()
        invoice.review_flags = review_flags
        return invoice

    # -------------------------------------------------------------------------
    # 4. Sales Returns / Credit Notes
    # -------------------------------------------------------------------------
    @staticmethod
    async def create_sales_return(
        session: AsyncSession,
        tenant_id: str,
        payload: SalesReturnCreateSchema,
    ) -> SalesReturn:
        """Process Sales Return, replenish Godown stock, and issue Credit Note in ledger."""
        # Resolve Godown
        godown_id = payload.godown_id
        if not godown_id:
            primary_godown = await session.scalar(
                select(Godown).where(
                    Godown.tenant_id == tenant_id,
                    Godown.is_primary == True,
                    Godown.is_active == True,
                )
            )
            if not primary_godown:
                raise ValueError("No active godown found for tenant")
            godown_id = primary_godown.id

        return_number = payload.return_number
        if not return_number:
            return_number = await BillingService.get_next_number(
                session=session,
                tenant_id=tenant_id,
                doc_type="SALES_RETURN",
                default_prefix="RET/26-27/",
            )

        return_id = str(uuid.uuid4())
        return_date = to_utc(payload.return_date) or datetime.now(timezone.utc)

        lines: List[SalesReturnLine] = []
        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")

        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product)
                .where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
                .options(selectinload(Product.units))
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            conv_factor = SmartUnitConverter.resolve_conversion_factor(
                product.units, line_in.unit_name, line_in.conversion_factor
            )
            base_qty = (line_in.quantity * conv_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            taxable = (line_in.quantity * line_in.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            gst_rate = line_in.gst_rate_percent if line_in.gst_rate_percent is not None else product.gst_rate_percent
            tax_amt = (taxable * (gst_rate / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            line_tot = taxable + tax_amt

            subtotal += taxable
            total_tax += tax_amt

            line_obj = SalesReturnLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                return_id=return_id,
                line_number=idx,
                product_id=product.id,
                unit_name=line_in.unit_name,
                conversion_factor=conv_factor,
                quantity=line_in.quantity,
                base_quantity=base_qty,
                unit_price=line_in.unit_price,
                taxable_amount=taxable,
                gst_rate_percent=gst_rate,
                tax_amount=tax_amt,
                line_total=line_tot,
                return_condition=getattr(line_in, "return_condition", "EXCESS") or "EXCESS",
            )
            lines.append(line_obj)

        grand_total = subtotal + total_tax

        sales_return = SalesReturn(
            id=return_id,
            tenant_id=tenant_id,
            return_number=return_number,
            return_date=return_date,
            original_invoice_id=payload.original_invoice_id,
            original_invoice_number=payload.original_invoice_number,
            party_id=payload.party_id,
            customer_name=payload.customer_name,
            godown_id=godown_id,
            refund_mode=payload.refund_mode,
            subtotal_amount=subtotal,
            total_tax_amount=total_tax,
            grand_total=grand_total,
            reason=payload.reason,
            notes=payload.notes,
            lines=lines,
        )
        session.add(sales_return)

        # Replenish Stock (+ base_quantity) at cost (WAC), never at the selling price
        # Only EXCESS / Good Condition items are added to sellable stock.
        # DAMAGED items are logged for audit but kept out of sellable inventory.
        for line in lines:
            sb = await session.scalar(
                select(StockBalance).where(
                    StockBalance.tenant_id == tenant_id,
                    StockBalance.godown_id == godown_id,
                    StockBalance.product_id == line.product_id,
                )
            )
            prod_cost = await session.scalar(
                select(Product.purchase_price_base).where(
                    Product.id == line.product_id, Product.tenant_id == tenant_id
                )
            ) or Decimal("0.0000")
            return_cost = (
                sb.weighted_avg_cost_base
                if sb and sb.weighted_avg_cost_base > Decimal("0")
                else prod_cost
            )

            is_damaged = line.return_condition == "DAMAGED"
            mov_type = "SALES_RETURN_DAMAGED" if is_damaged else "SALES_RETURN"
            doc_num = f"{sales_return.return_number} (DAMAGED)" if is_damaged else sales_return.return_number

            sm = StockMovement(
                tenant_id=tenant_id,
                godown_id=godown_id,
                product_id=line.product_id,
                movement_type=mov_type,
                quantity_base=line.base_quantity,
                unit_cost_base=return_cost,
                reference_doc_type="SALES_RETURN",
                reference_doc_id=sales_return.id,
                reference_doc_number=doc_num,
            )
            session.add(sm)

            if not is_damaged:
                if sb:
                    sb.current_quantity_base += line.base_quantity
                    sb.last_movement_at = return_date
                else:
                    sb = StockBalance(
                        tenant_id=tenant_id,
                        godown_id=godown_id,
                        product_id=line.product_id,
                        current_quantity_base=line.base_quantity,
                        weighted_avg_cost_base=return_cost,
                        last_movement_at=return_date,
                    )
                    session.add(sb)
                    await session.flush()  # make the new balance visible to later lines (autoflush is off)

        # Financial Ledger Update
        if payload.party_id and payload.refund_mode == "CREDIT_NOTE":
            party = await session.scalar(
                select(Party).where(Party.id == payload.party_id, Party.tenant_id == tenant_id)
            )
            if party:
                le = LedgerEntry(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    party_id=party.id,
                    entry_type="SALES_RETURN_CREDIT_NOTE",
                    debit_amount=Decimal("0.00"),
                    credit_amount=grand_total,
                    reference_doc_type="SALES_RETURN",
                    reference_doc_id=sales_return.id,
                    reference_doc_number=sales_return.return_number,
                    entry_date=ist_date_of(return_date),
                    notes=f"Sales Return Credit Note {sales_return.return_number}",
                )
                session.add(le)
                party.current_balance -= grand_total

                # Settle the credit note against the original bill's open due; any excess stays
                # unallocated (customer advance). Keeps: unpaid invoices - advances == balance.
                if payload.original_invoice_id:
                    inv_entry = await session.scalar(
                        select(LedgerEntry).where(
                            LedgerEntry.tenant_id == tenant_id,
                            LedgerEntry.party_id == party.id,
                            LedgerEntry.entry_type == "SALES_INVOICE",
                            LedgerEntry.reference_doc_id == payload.original_invoice_id,
                        )
                    )
                    if inv_entry:
                        already_allocated = await session.scalar(
                            select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), Decimal("0"))).where(
                                PaymentAllocation.tenant_id == tenant_id,
                                PaymentAllocation.invoice_entry_id == inv_entry.id,
                            )
                        ) or Decimal("0")
                        open_due = max(Decimal("0.00"), inv_entry.debit_amount - already_allocated)
                        settle = min(grand_total, open_due).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
                        if settle > Decimal("0.00"):
                            session.add(
                                PaymentAllocation(
                                    id=str(uuid.uuid4()),
                                    tenant_id=tenant_id,
                                    payment_entry_id=le.id,
                                    invoice_entry_id=inv_entry.id,
                                    allocated_amount=settle,
                                )
                            )

        await session.commit()
        return sales_return

    # -------------------------------------------------------------------------
    # 5. Quotations / Estimates
    # -------------------------------------------------------------------------
    @staticmethod
    async def create_quotation(
        session: AsyncSession,
        tenant_id: str,
        payload: QuotationCreateSchema,
    ) -> Quotation:
        """Create a quotation / price estimate for contractors or retail buyers without moving stock."""
        # Resolve Godown
        godown_id = payload.godown_id
        if not godown_id:
            primary_godown = await session.scalar(
                select(Godown).where(
                    Godown.tenant_id == tenant_id,
                    Godown.is_primary == True,
                    Godown.is_active == True,
                )
            )
            if not primary_godown:
                raise ValueError("No active godown found for tenant")
            godown_id = primary_godown.id

        # Resolve Price List (explicit > party's tier > default)
        price_list_id = payload.price_list_id
        if not price_list_id and payload.party_id:
            price_list_id = await session.scalar(
                select(Party.price_list_id).where(Party.id == payload.party_id, Party.tenant_id == tenant_id)
            )
        if not price_list_id:
            default_pl = await session.scalar(
                select(PriceList).where(
                    PriceList.tenant_id == tenant_id,
                    PriceList.is_default == True,
                )
            )
            price_list_id = default_pl.id if default_pl else None
            if not price_list_id:
                any_pl = await session.scalar(select(PriceList).where(PriceList.tenant_id == tenant_id))
                price_list_id = any_pl.id if any_pl else "RETAIL"

        quotation_number = payload.quotation_number
        if not quotation_number:
            quotation_number = await BillingService.get_next_number(
                session=session,
                tenant_id=tenant_id,
                doc_type="QUOTATION",
                default_prefix="QT/26-27/",
            )

        quote_id = str(uuid.uuid4())
        quote_date = payload.quotation_date or datetime.now(timezone.utc)

        lines: List[QuotationLine] = []
        subtotal = Decimal("0.00")
        total_discount = Decimal("0.00")
        total_tax = Decimal("0.00")

        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product).where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            gross = (line_in.quantity * line_in.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            disc = min(line_in.discount_amount, gross).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            taxable = gross - disc
            gst_rate = line_in.gst_rate_percent if line_in.gst_rate_percent is not None else product.gst_rate_percent
            tax_amt = (taxable * (gst_rate / Decimal("100"))).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            line_tot = taxable + tax_amt

            subtotal += taxable
            total_discount += disc
            total_tax += tax_amt

            line_obj = QuotationLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                quotation_id=quote_id,
                line_number=idx,
                product_id=product.id,
                unit_name=line_in.unit_name,
                conversion_factor=line_in.conversion_factor,
                quantity=line_in.quantity,
                unit_price=line_in.unit_price,
                discount_amount=disc,
                taxable_amount=taxable,
                gst_rate_percent=gst_rate,
                tax_amount=tax_amt,
                line_total=line_tot,
            )
            lines.append(line_obj)

        exact_total = subtotal + total_tax
        grand_total = exact_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP).quantize(TWO_PLACES)
        round_off = (grand_total - exact_total).quantize(TWO_PLACES)

        quote = Quotation(
            id=quote_id,
            tenant_id=tenant_id,
            quotation_number=quotation_number,
            quotation_date=quote_date,
            valid_until=payload.valid_until,
            party_id=payload.party_id,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            price_list_id=price_list_id,
            godown_id=godown_id,
            place_of_supply_state_code=payload.place_of_supply_state_code,
            status="OPEN",
            subtotal_amount=subtotal,
            discount_amount=total_discount,
            total_tax_amount=total_tax,
            round_off_amount=round_off,
            grand_total=grand_total,
            notes=payload.notes,
            lines=lines,
        )
        session.add(quote)
        await session.commit()
        return quote

    @staticmethod
    async def convert_quotation_to_invoice(
        session: AsyncSession,
        tenant_id: str,
        quotation_id: str,
        payment_mode: str = "CASH",
        paid_amount: Optional[Decimal] = None,
    ) -> SalesInvoice:
        """1-Click convert open quotation into a real posted SalesInvoice."""
        quote = await session.scalar(
            select(Quotation)
            .where(Quotation.id == quotation_id, Quotation.tenant_id == tenant_id)
            .options(selectinload(Quotation.lines))
        )
        if not quote:
            raise ValueError(f"Quotation {quotation_id} not found")
        if quote.status != "OPEN":
            raise ValueError(f"Quotation is already {quote.status}")

        # Map quotation lines to SalesInvoice lines
        from app.schemas.billing import SalesInvoiceLineInputSchema
        invoice_lines_input: List[SalesInvoiceLineInputSchema] = []
        for ql in quote.lines:
            invoice_lines_input.append(
                SalesInvoiceLineInputSchema(
                    product_id=ql.product_id,
                    unit_name=ql.unit_name,
                    conversion_factor=ql.conversion_factor,
                    quantity=ql.quantity,
                    unit_price=ql.unit_price,
                    discount_type="FLAT",
                    discount_value=ql.discount_amount,
                    gst_rate_percent=ql.gst_rate_percent,
                )
            )

        invoice_payload = SalesInvoiceCreateSchema(
            party_id=quote.party_id,
            customer_name=quote.customer_name,
            customer_phone=quote.customer_phone,
            place_of_supply_state_code=quote.place_of_supply_state_code,
            price_list_id=quote.price_list_id,
            godown_id=quote.godown_id,
            payment_mode=payment_mode,
            paid_amount=paid_amount,
            lines=invoice_lines_input,
        )

        invoice = await BillingService.create_sales_invoice(
            session=session,
            tenant_id=tenant_id,
            payload=invoice_payload,
        )

        # Update quotation status
        quote.status = "CONVERTED"
        quote.converted_invoice_id = invoice.id
        await session.commit()

        return invoice

    # -------------------------------------------------------------------------
    # 6. Delivery Challans
    # -------------------------------------------------------------------------
    @staticmethod
    async def create_delivery_challan(
        session: AsyncSession,
        tenant_id: str,
        payload: DeliveryChallanCreateSchema,
    ) -> DeliveryChallan:
        """Issue Delivery Challan moving physical goods from godown to vehicle/site."""
        godown_id = payload.godown_id
        if not godown_id:
            primary_godown = await session.scalar(
                select(Godown).where(
                    Godown.tenant_id == tenant_id,
                    Godown.is_primary == True,
                    Godown.is_active == True,
                )
            )
            if not primary_godown:
                raise ValueError("No active godown found for tenant")
            godown_id = primary_godown.id

        challan_number = payload.challan_number
        if not challan_number:
            challan_number = await BillingService.get_next_number(
                session=session,
                tenant_id=tenant_id,
                doc_type="DELIVERY_CHALLAN",
                default_prefix="DC/26-27/",
            )

        challan_id = str(uuid.uuid4())
        challan_date = payload.challan_date or datetime.now(timezone.utc)

        lines: List[DeliveryChallanLine] = []
        grand_total = Decimal("0.00")

        for idx, line_in in enumerate(payload.lines, start=1):
            product = await session.scalar(
                select(Product)
                .where(Product.id == line_in.product_id, Product.tenant_id == tenant_id)
                .options(selectinload(Product.units))
            )
            if not product:
                raise ValueError(f"Product {line_in.product_id} not found")

            conv_factor = SmartUnitConverter.resolve_conversion_factor(
                product.units, line_in.unit_name, line_in.conversion_factor
            )
            base_qty = (line_in.quantity * conv_factor).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
            line_tot = (line_in.quantity * line_in.unit_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            grand_total += line_tot

            line_obj = DeliveryChallanLine(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                challan_id=challan_id,
                line_number=idx,
                product_id=product.id,
                unit_name=line_in.unit_name,
                conversion_factor=conv_factor,
                quantity=line_in.quantity,
                base_quantity=base_qty,
                unit_price=line_in.unit_price,
                line_total=line_tot,
            )
            lines.append(line_obj)

        dc = DeliveryChallan(
            id=challan_id,
            tenant_id=tenant_id,
            challan_number=challan_number,
            challan_date=challan_date,
            party_id=payload.party_id,
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            delivery_site_address=payload.delivery_site_address,
            vehicle_number=payload.vehicle_number,
            godown_id=godown_id,
            status="DISPATCHED",
            subtotal_amount=grand_total,
            grand_total=grand_total,
            notes=payload.notes,
            lines=lines,
        )
        session.add(dc)

        # Move stock immediately upon physical dispatch (valued at WAC cost, not selling price)
        for line in lines:
            sb = await session.scalar(
                select(StockBalance).where(
                    StockBalance.tenant_id == tenant_id,
                    StockBalance.godown_id == godown_id,
                    StockBalance.product_id == line.product_id,
                )
            )
            prod_cost = await session.scalar(
                select(Product.purchase_price_base).where(
                    Product.id == line.product_id, Product.tenant_id == tenant_id
                )
            ) or Decimal("0.0000")
            dispatch_cost = (
                sb.weighted_avg_cost_base
                if sb and sb.weighted_avg_cost_base > Decimal("0")
                else prod_cost
            )

            sm = StockMovement(
                tenant_id=tenant_id,
                godown_id=godown_id,
                product_id=line.product_id,
                movement_type="DELIVERY_CHALLAN",
                quantity_base=-line.base_quantity,
                unit_cost_base=dispatch_cost,
                reference_doc_type="DELIVERY_CHALLAN",
                reference_doc_id=dc.id,
                reference_doc_number=dc.challan_number,
            )
            session.add(sm)

            if sb:
                sb.current_quantity_base -= line.base_quantity
                sb.last_movement_at = challan_date
            else:
                sb = StockBalance(
                    tenant_id=tenant_id,
                    godown_id=godown_id,
                    product_id=line.product_id,
                    current_quantity_base=-line.base_quantity,
                    weighted_avg_cost_base=dispatch_cost,
                    last_movement_at=challan_date,
                )
                session.add(sb)
                await session.flush()  # make the new balance visible to later lines (autoflush is off)

        await session.commit()
        return dc

    @staticmethod
    async def convert_challan_to_invoice(
        session: AsyncSession,
        tenant_id: str,
        challan_id: str,
        payment_mode: str = "CREDIT",
        paid_amount: Optional[Decimal] = None,
    ) -> SalesInvoice:
        """Convert a dispatched delivery challan into a final bill without double-deducting stock."""
        dc = await session.scalar(
            select(DeliveryChallan)
            .where(DeliveryChallan.id == challan_id, DeliveryChallan.tenant_id == tenant_id)
            .options(selectinload(DeliveryChallan.lines))
        )
        if not dc:
            raise ValueError(f"Delivery Challan {challan_id} not found")
        if dc.status == "INVOICED":
            raise ValueError("Delivery Challan has already been invoiced")

        from app.schemas.billing import SalesInvoiceLineInputSchema
        invoice_lines_input: List[SalesInvoiceLineInputSchema] = []
        for cl in dc.lines:
            invoice_lines_input.append(
                SalesInvoiceLineInputSchema(
                    product_id=cl.product_id,
                    unit_name=cl.unit_name,
                    conversion_factor=cl.conversion_factor,
                    quantity=cl.quantity,
                    unit_price=cl.unit_price,
                    discount_type="FLAT",
                    discount_value=Decimal("0.00"),
                )
            )

        invoice_payload = SalesInvoiceCreateSchema(
            party_id=dc.party_id,
            customer_name=dc.customer_name,
            customer_phone=dc.customer_phone,
            godown_id=dc.godown_id,
            payment_mode=payment_mode,
            paid_amount=paid_amount,
            delivery_challan_id=dc.id,  # Signals engine to skip stock deduction
            lines=invoice_lines_input,
        )

        invoice = await BillingService.create_sales_invoice(
            session=session,
            tenant_id=tenant_id,
            payload=invoice_payload,
        )

        return invoice
