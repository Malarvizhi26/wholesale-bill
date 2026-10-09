# Module 3 Specification: Customer & Supplier Ledger
**Version:** 1.0.0  
**Target:** FastAPI Backend + Next.js Back Office  
**Primary Benchmark:** The ledger balance for any party equals the sum of their open invoices minus unallocated payments, down to the exact paisa (0.01 INR).

---

## 1. Entities & Data Contracts

### 1.1 Party Master Schema
```typescript
interface PartyMasterInput {
  partyType: 'CUSTOMER' | 'SUPPLIER' | 'BOTH';
  name: string;
  phone: string;
  email?: string;
  gstin?: string; // Validated via regex + checksum for B2B
  stateCode: string; // e.g. "33" for Tamil Nadu
  billingAddress: string;
  priceListCode: 'RETAIL' | 'WHOLESALE' | 'CONTRACTOR';
  creditLimit: number;
  creditDays: number; // e.g. 15, 30, 45 days
  openingBalance: number; // Positive = owes us, Negative = advance
}
```

### 1.2 Receipt / Payment Voucher Schema
```typescript
interface PaymentAllocationInput {
  invoiceEntryId: string; // ID of the debit ledger_entry
  amount: number;
}

interface ReceiptVoucherInput {
  partyId: string;
  voucherDate: string;
  paymentMode: 'CASH' | 'UPI' | 'NEFT_RTGS' | 'CHEQUE';
  referenceNumber?: string; // UTR or Cheque number
  totalAmount: number;
  allocationMethod: 'OLDEST_FIRST' | 'MANUAL';
  manualAllocations?: PaymentAllocationInput[];
  notes?: string;
}
```

---

## 2. Business Rules & Logic

### 2.1 Double-Entry Append-Only Rules
1. **Debit (`debit_amount`)**:
   - Customer sales invoices.
   - Payments made to suppliers.
   - Customer debit notes / interest charges.
   - Debit increases the amount the customer owes the business.
2. **Credit (`credit_amount`)**:
   - Payments received from customers.
   - Supplier purchase bills.
   - Sales returns / customer credit notes.
   - Credit decreases the amount the customer owes the business.
3. **Current Balance Invariant**:
   $$\text{Current Balance} = \text{Opening Balance} + \sum \text{Debit Amounts} - \sum \text{Credit Amounts}$$
   - Positive balance = Party owes us money (Asset/Receivable).
   - Negative balance = We owe party money (Advance/Payable).

### 2.2 Payment Allocation & Ageing Buckets
1. **FIFO (Oldest-First) Auto-Allocation**:
   - Fetch all open invoices (debit entries where $\text{Allocated Amount} < \text{Debit Amount}$) ordered by `entry_date ASC`.
   - Distribute the receipt amount sequentially until exhausted.
   - Any remaining receipt funds are recorded with no allocation ("On Account" advance balance).
2. **Ageing Buckets**:
   For each unpaid or partially-paid invoice:
   $$\text{Age (days)} = \text{Current Date} - \text{Invoice Date}$$
   - **Current / 0–30 Days**: Fresh dues within normal credit window.
   - **31–60 Days**: Due; soft reminders triggered.
   - **61–90 Days**: Overdue; owner warning on POS billing.
   - **90+ Days**: Critical risk; automated credit freeze.

### 2.3 Collection Engine & WhatsApp Reminders
1. **Today's Call List for Owner**:
   - Query parties where `current_balance > 0` and oldest overdue invoice age exceeds `party.credit_days`.
   - Ranked by score: $\text{Overdue Amount} \times \sqrt{\text{Days Overdue}}$.
2. **One-Click WhatsApp Reminder**:
   - Generates statement summary:
     > *"Vanakkam [Customer Name], balance due to [Shop Name] is ₹[Amount]. Oldest bill [Bill No] is [Days] days overdue. Pay instantly via UPI: [Payment Link]."*
   - Generates Statement of Account PDF and sends via MSG91 WhatsApp Business API.
3. **Webhook Auto-Reconciliation**:
   - Payments received through Cashfree/Razorpay UPI link trigger webhook `/api/v1/payments/webhook`.
   - Automatically posts `PAYMENT_RECEIPT` into `ledger_entries` and allocates against the specific invoice.

---

## 3. Acceptance Tests

- [ ] **Paisa-Level Ledger Integrity**: Generate 50 sales invoices and 20 partial payments with arbitrary odd paisa values. Run verification script: $\sum \text{Unpaid Invoices} - \text{Unallocated Advances} == \text{party.current_balance}$ with $0.00$ discrepancy.
- [ ] **FIFO Settlement Allocation**: Customer has Bill 1 (₹2,500 on Sep 1) and Bill 2 (₹4,000 on Sep 10). Receipt of ₹3,000 received with `OLDEST_FIRST`: Bill 1 is 100% settled; Bill 2 has ₹500 settled, ₹3,500 open.
- [ ] **Ageing Bucket Classification**: Query ageing report on Day 65 since invoice issue date: line item appears strictly in the `61–90 Days` column.
- [ ] **Credit Limit Freeze**: If customer exceeds credit limit, POS prevents new credit bill unless Owner PIN is supplied.
