# Module 1 Specification: Fast Billing (POS)
**Version:** 1.0.0  
**Target:** Desktop Counter (Tauri + React + SQLite) & Back Office Web (Next.js)  
**Primary Benchmark:** 5-line cash bill completed in under 30 seconds keyboard-only without mouse.

---

## 1. Entities & Data Contracts

### 1.1 Draft Bill State (In-Memory / SQLite Local Store)
```typescript
interface BillLineItem {
  id: string; // temp client uuid
  lineNumber: number;
  productId: string;
  productCode: string;
  name: string;
  tamilName?: string;
  hsnCode: string;
  unitName: string;
  availableUnits: Array<{
    unitName: string;
    conversionFactor: number;
    price: number;
    canSell: boolean;
  }>;
  quantity: number;
  isVariableWeight: boolean;
  actualWeightKg?: number; // e.g. weighed TMT rod or GI sheet
  baseQuantity: number;
  unitPrice: number;
  costPriceBaseAtSale: number;
  discountType: 'PERCENT' | 'FLAT';
  discountValue: number;
  discountAmount: number;
  taxableAmount: number;
  gstRatePercent: number;
  cgstAmount: number;
  sgstAmount: number;
  igstAmount: number;
  lineTotal: number;
}

interface BillState {
  billId: string;
  invoiceNumber: string; // From reserved device series
  partyId?: string; // null for Walk-in Retail
  partyName: string;
  partyPhone?: string;
  partyGstin?: string;
  priceListId: string;
  godownId: string;
  isB2B: boolean;
  placeOfSupplyStateCode: string;
  lines: BillLineItem[];
  subtotal: number;
  totalDiscount: number;
  cgstTotal: number;
  sgstTotal: number;
  igstTotal: number;
  taxTotal: number;
  roundOff: number;
  grandTotal: number;
  paidAmount: number;
  paymentMode: 'CASH' | 'UPI' | 'CARD' | 'CREDIT' | 'SPLIT';
  paymentBreakdown: Array<{
    mode: 'CASH' | 'UPI' | 'CARD' | 'CREDIT';
    amount: number;
    referenceNo?: string;
  }>;
  status: 'DRAFT' | 'HELD' | 'POSTED';
  heldAt?: string;
}
```

---

## 2. Business Rules & Logic

### 2.1 Fast Keyboard Control Loop
| Key | Action | Focus Target |
|---|---|---|
| `F2` | Clear / Start New Bill | First Line Search Input |
| `F3` | Focus Product Search | Product autocomplete drop-down |
| `F4` | Focus Customer Selection | Customer autocomplete drop-down |
| `F6` | Toggle Hold Current Bill | Shifts bill to Hold Tray; opens blank bill |
| `F7` | Recall Bill from Hold Tray | Opens modal to pick held bill (arrow keys + Enter) |
| `F8` | Split Payment Dialog | Opens modal for Cash + UPI + Credit breakdown |
| `F9` | Quick Cash Bill & Print | Finalizes bill as Cash, prints thermal, resets to F2 |
| `F10` | Full Save & Print Dialog | Allows payment selection, A4 vs Thermal choice |
| `Escape` | Close Modal / Cancel Action | Returns to active bill line |

### 2.2 Pricing & Contractor Guardrails
1. When a party is selected, their default `price_list_id` is applied to all existing and future lines in the current bill.
2. If the user edits the line `unitPrice`:
   - If `unitPrice < costPriceBaseAtSale * conversionFactor`: The POS raises a warning: `"Price below purchase cost (₹{cost})"`. Requires entering **Owner PIN** to post.
   - If `unitPrice` is adjusted outside the allowed range (`min_allowed_price` to `max_allowed_price`), the deviation is logged in `audit_events`.
3. **Credit Limit Check**:
   - If `paymentMode == 'CREDIT'` or any credit amount is allocated:
     ```typescript
     projectedBalance = party.currentBalance + creditAmount;
     if (party.creditLimit > 0 && projectedBalance > party.creditLimit) {
       // Trigger Credit Limit Breach Warning
       // Requires Owner Override PIN to proceed
     }
     ```

### 2.3 Tax & Round-Off Calculation Engine
1. **Intra-State (In-State) vs Inter-State**:
   - If `placeOfSupplyStateCode === shopStateCode` (default `'33'` for Tamil Nadu):
     - `cgstPercent = gstRatePercent / 2`
     - `sgstPercent = gstRatePercent / 2`
     - `igstPercent = 0.00`
   - Otherwise:
     - `cgstPercent = 0.00`
     - `sgstPercent = 0.00`
     - `igstPercent = gstRatePercent`
2. **Formula per Line**:
   ```typescript
   grossAmount = quantity * unitPrice;
   discountAmount = discountType === 'PERCENT' 
     ? round2(grossAmount * (discountValue / 100))
     : round2(discountValue);
   taxableAmount = round2(grossAmount - discountAmount);
   cgstAmount = round2(taxableAmount * (cgstPercent / 100));
   sgstAmount = round2(taxableAmount * (sgstPercent / 100));
   igstAmount = round2(taxableAmount * (igstPercent / 100));
   lineTotal = round2(taxableAmount + cgstAmount + sgstAmount + igstAmount);
   ```
3. **Bill Total & Round-Off**:
   ```typescript
   exactTotal = sum(lineTotals);
   grandTotal = Math.round(exactTotal);
   roundOff = round2(grandTotal - exactTotal); // between -0.49 and +0.50
   ```

### 2.4 Dynamic UPI QR Generation
- Construct UPI intent payload:
  `upi://pay?pa={upi_vpa}&pn={business_name}&am={grand_total}&cu=INR&tn=Invoice_{invoice_number}`
- Rendered on screen for customer scanning and printed directly as a QR code raster at the bottom of the thermal receipt.

### 2.5 Offline Billing & Conflict Resolution
1. Each counter device stores local product master, price lists, customer balances, and pre-allocated number series: `C{device_id}/26-27/{seq:04d}`.
2. Offline bills are marked `is_offline_created = true` and queued in SQLite `sync_queue`.
3. When network restores:
   - Client sends queued invoices to `/api/v1/billing/sync-invoices`.
   - Server registers invoices, creates `stock_movements`, updates `stock_balances`, and posts `ledger_entries`.
   - If stock goes negative or credit limit is exceeded during offline sync, **the invoice is NOT rejected**; an alert is flagged on the Owner Dashboard for review.

---

## 3. Acceptance Tests

- [ ] **Fast Bill Benchmark**: Input 5 products via keyboard barcodes / search, select cash, press F9; total time <= 28 seconds.
- [ ] **Credit Limit Enforcement**: Customer with limit ₹10,000 and current balance ₹8,000 attempts ₹3,000 credit sale. Prompt requires 4-digit Owner PIN before posting.
- [ ] **Variable Weight Calculation**: 10 rods of 12mm TMT added (default 106.5 kg), clerk enters actual weighed scale output of 104.2 kg. Stock movement records `-104.2000 kg` base stock deduction.
- [ ] **Offline Sync Invariance**: Turn off network on Counter 1. Bill 3 invoices. Reconnect. Verify invoices appear on Server with identical numbering, and stock ledger decrements correctly.
