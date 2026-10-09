# Module 2 Specification: Smart Inventory & Stock Ledger
**Version:** 1.0.0  
**Target:** FastAPI Backend + Next.js Back Office  
**Primary Benchmark:** Purchasing 10 boxes of 100 screws and selling 37 pieces shows exactly "9 boxes 63 pieces (963 pcs)" across all godown views, reports, and valuations.

---

## 1. Entities & Data Contracts

### 1.1 Product Master Schema
```typescript
interface ProductMasterInput {
  code: string;
  name: string;
  tamilName?: string;
  categoryId?: string;
  brandId?: string;
  hsnCode: string; // 4 to 8 digits
  baseUnit: 'piece' | 'kg' | 'metre' | 'sqft' | 'litre';
  isVariableWeight: boolean; // true for TMT rods, steel sheets, MS pipes
  minStockBase: number;
  reorderQuantityBase: number;
  units: Array<{
    unitName: string; // e.g. "Box", "Coil", "Bundle", "Tonne"
    conversionFactor: number; // multiplier to base unit
    canBuy: boolean;
    canSell: boolean;
    barcode?: string;
    isDefaultSales: boolean;
    isDefaultPurchase: boolean;
  }>;
  prices: Array<{
    priceListCode: 'RETAIL' | 'WHOLESALE' | 'CONTRACTOR';
    unitName: string;
    sellingPrice: number;
    minAllowedPrice?: number;
  }>;
  initialStock?: Array<{
    godownId: string;
    unitName: string;
    quantity: number;
    purchaseCostPerUnit: number;
  }>;
}
```

### 1.2 Purchase Bill Entry & Landed Cost Breakdown
```typescript
interface PurchaseBillLine {
  productId: string;
  unitName: string;
  conversionFactor: number;
  quantity: number;
  unitPurchasePrice: number;
  discountAmount: number;
  taxableAmount: number;
  gstRatePercent: number;
  taxAmount: number;
  lineTotal: number;
  baseQuantity: number;
  landedCostBase: number; // Computed after absorbing freight/loading
}

interface PurchaseBillInput {
  supplierId: string;
  supplierInvoiceNumber: string;
  billDate: string;
  godownId: string;
  lines: PurchaseBillLine[];
  freightCharges: number; // Transport cost to distribute
  loadingCharges: number; // Hamali/unloading cost to distribute
  otherExpenses: number;
  roundOff: number;
  totalInvoiceAmount: number;
}
```

---

## 2. Business Rules & Logic

### 2.1 Smart Unit Conversion Engine
1. **Base Unit Rule**: The base unit is the atomic sellable unit.
2. **Representation Formatter**:
   ```typescript
   function formatMixedUnits(totalBaseQty: number, units: ProductUnit[]): string {
     // Sort units descending by conversion factor (excluding base)
     const sortedUnits = [...units]
       .filter(u => u.conversionFactor > 1)
       .sort((a, b) => b.conversionFactor - a.conversionFactor);

     let remaining = totalBaseQty;
     const parts: string[] = [];

     for (const unit of sortedUnits) {
       const count = Math.floor(remaining / unit.conversionFactor);
       if (count > 0) {
         parts.push(`${count} ${unit.unitName}`);
         remaining = remaining % unit.conversionFactor;
       }
     }

     if (remaining > 0 || parts.length === 0) {
       parts.push(`${Number(remaining.toFixed(4))} ${units[0].baseUnit}`);
     }

     return `${parts.join(' ')} (${totalBaseQty} ${units[0].baseUnit})`;
   }
   // Example: 963 pieces (Box = 100 pcs) => "9 Box 63 piece (963 piece)"
   ```

### 2.2 Landed Cost & Weighted Average Cost (WAC) Engine
1. **Landed Cost Distribution**:
   Freight and loading costs are apportioned across bill lines proportional to their taxable amount:
   $$\text{Apportioned Overhead}_i = (\text{Freight} + \text{Loading}) \times \frac{\text{Taxable Amount}_i}{\sum \text{Taxable Amount}}$$
   $$\text{Landed Cost Base}_i = \frac{\text{Taxable Amount}_i - \text{Line Discounts}_i + \text{Apportioned Overhead}_i}{\text{Base Quantity}_i}$$

2. **Weighted Average Cost Formula**:
   When inward stock arrives:
   $$\text{WAC}_{\text{new}} = \frac{(Q_{\text{current}} \times \text{WAC}_{\text{current}}) + (Q_{\text{inward}} \times C_{\text{landed\_base}})}{Q_{\text{current}} + Q_{\text{inward}}}$$
   - If current stock $Q_{\text{current}} \le 0$, $\text{WAC}_{\text{new}} = C_{\text{landed\_base}}$.
   - Outward stock movements (sales, scrap, damage adjustments) leave $\text{WAC}$ unchanged.

### 2.3 Append-Only Stock Ledger (`stock_movements`)
- Every transaction writes an immutable row into `stock_movements`.
- The `stock_balances` cache row is updated in the same database transaction.
- **Negative Stock Permitted**:
  - In hardware retail, customers frequently take goods before the supplier bill is posted.
  - Transactions decrement stock into negative values without throwing an abort error.
  - A negative stock event creates an alert in `stock_alerts` for owner attention.

### 2.4 Godown Transfers & Stock Adjustments
- **Godown Transfer**: Creates paired rows in `stock_movements`:
  1. `TRANSFER_OUT` on source godown (`-Q`).
  2. `TRANSFER_IN` on target godown (`+Q`) with the source godown's current $\text{WAC}$.
- **Stock Adjustment**:
  - Types: `BREAKAGE`, `THEFT`, `EXPIRY`, `COUNT_CORRECTION`.
  - Discrepancy > ₹1,000 value requires Owner PIN confirmation.

---

## 3. Acceptance Tests

- [ ] **Smart Unit Decomposition**: Buy 10 boxes (100 pcs/box). Sell 37 pcs. Query godown balance: returns `9 Box 63 piece (963 piece)`.
- [ ] **Landed Cost Apportionment**: Purchase 10 bags Cement at ₹400/bag and 2 bundles Rods at ₹3,000/bundle. Total goods = ₹10,000. Add ₹500 freight. Verify Cement landed cost absorbed ₹20/bag ($500 \times \frac{4000}{10000} \div 10$).
- [ ] **Weighted Average Recalculation**: Current stock = 10 pcs @ ₹100. Inward 10 pcs @ ₹120. New average cost is ₹110. Sell 5 pcs; average cost remains ₹110; remaining stock = 15 pcs.
- [ ] **Excel Bulk Import**: Upload 500-line sample hardware inventory CSV/Excel with categories, base units, and box conversions. Complete preview, validate errors, and commit in < 3 seconds.
