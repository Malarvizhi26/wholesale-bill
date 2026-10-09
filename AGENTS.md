# AGENTS.md — Hardware Billing OS Developer & AI Agent Guide
**Authoritative Specification for Code Generation & Feature Implementation**  
**Version:** 1.0.0 (October 2026)  
**Target:** Single-location hardware & building material shops in Tamil Nadu  

---

## 1. Project Overview & Core Philosophy

This system is **"the shop's daily business manager, not an invoice printer."**  
It solves three critical problems generic software fails to address:
1. **Smart Unit Conversion**: Buying in bulk units (boxes, coils, tonnes) and selling in smaller or fractional units (pieces, metres, kg, rods) with $100\%$ inventory exactness.
2. **Contractor Tiered Pricing**: Auto-applying Retail, Wholesale, and Contractor price lists based on customer profiles with floor price protections.
3. **Party Credit Ledger**: Tracking bill-wise dues, ageing buckets, and credit limits with WhatsApp collections.

### Core Design Rule
> **A counter clerk with zero software training must finish a 5-line cash bill in under 30 seconds using keyboard only.**

---

## 2. Technology Stack & Directory Structure

| Layer | Technology | Key Responsibility |
|---|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2 | Modular monolith exposing REST API and WebSocket sync |
| **Database** | PostgreSQL 16 with Row-Level Security (RLS) | Multi-tenant shared schema, append-only financial and stock ledgers |
| **Worker / Queue** | Celery + Redis | Asynchronous tasks, WhatsApp dispatch, scheduled reports, daily backups |
| **Back Office Web** | Next.js 14+ (App Router), TanStack Query, Tailwind CSS, shadcn/ui | Owner & accountant dashboard, master catalogue, ledger, reports |
| **Billing Counter** | Tauri desktop (React UI + local SQLite + sync queue) | Ultra-fast offline counter billing, ESC/POS thermal printing, barcode scanners |

### Standard Directory Tree
```text
billing/
├── AGENTS.md                         # This file: authoritative master contract
├── Hardware-Billing-OS-Development-Plan.docx
├── docs/
│   ├── DATA_MODEL.md                 # Complete PostgreSQL DDL & ERD
│   └── specs/
│       ├── billing.md                # POS module deep-dive spec
│       ├── inventory.md              # Smart inventory & stock ledger spec
│       └── ledger.md                 # Party ledger & credit management spec
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                     # config, database, rls_session, security
│   │   ├── models/                   # SQLAlchemy ORM models
│   │   ├── schemas/                  # Pydantic schemas
│   │   ├── modules/
│   │   │   ├── billing/              # invoices, lines, pos sessions, print templates
│   │   │   ├── inventory/            # products, units, conversions, godowns, movements
│   │   │   ├── ledger/               # parties, ledger_entries, allocations, reminders
│   │   │   ├── reports/              # sales, margin, stock valuation, gstr1, gstr3b
│   │   │   └── ai_assistant/         # safe tool definitions, prompt templates
│   │   └── tests/
│   ├── alembic/
│   └── Dockerfile
├── web/                              # Next.js Back Office
└── desktop/                          # Tauri Offline POS Desktop App
```

---

## 3. Universal Architectural Constraints & Guardrails

### 3.1 Tenancy & RLS Invariant
1. Every query must run with tenant isolation enforced at the database level:
   ```sql
   SET LOCAL app.current_tenant_id = '<current_tenant_uuid>';
   ```
2. Any newly created table **must** include:
   - `tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE RESTRICT`
   - An RLS policy enabling tenant-scoped `SELECT`, `INSERT`, `UPDATE`, `DELETE`.
3. Multi-tenancy leak prevention: Automated test suites must verify that Tenant A cannot access Tenant B's data under any condition.

### 3.2 Unit Math & Stock Storage
1. Stock is stored **strictly in base units** as `NUMERIC(18, 4)`.
2. Do not store text like `"2 boxes and 37 pieces"` in the database. Use formatting helpers to decompose base units for display.
3. Variable-weight items (e.g., TMT steel rods, GI sheets):
   - Formula: `base_quantity = actual_weight_kg` if entered; otherwise `quantity * conversion_factor`.
   - Stock always moves by actual weight.

### 3.3 Financial Calculations & Rounding
1. Line taxable amount: `round(quantity * unit_price - discount_amount, 2)`
2. Line tax amounts (CGST, SGST, IGST): `round(taxable_amount * (rate / 100), 2)`
3. Bill grand total: `round(sum(line_totals))`
4. Bill round-off: `round(grand_total - sum(line_totals), 2)` (strictly within $[-0.49, +0.50]$)

---

## 4. Module Specifications

### Module 1: Fast Billing (POS)
- **Keyboard Shortcuts**: `F2` (New Bill), `F3` (Item Search), `F4` (Customer), `F6` (Hold), `F7` (Recall), `F8` (Split Pay), `F9` (Quick Cash & Print), `F10` (Full Settle).
- **Offline Billing**:
  - Each desktop device issues invoices using its allocated series prefix (e.g. `C1/2026-27/0001`).
  - Saved locally in SQLite `sync_queue` and printed immediately.
  - Pushed to server when internet reconnects.
  - Server accepts offline invoices; conflicts (negative stock or credit exceeded) are flagged for owner review, never rejected.
- **Dynamic UPI QR**: Formats UPI intent string with invoice ID and grand total for zero-friction digital collection.
- **Printing**: Direct raw ESC/POS byte streaming to 2" and 3" thermal printers (bypassing browser dialog).

### Module 2: Smart Inventory & Stock Ledger
- **Append-Only Ledger**: `stock_movements` is strictly append-only.
- **Costing Engine**: Weighted Average Cost (WAC) calculated on every inward stock movement:
  $$\text{WAC}_{\text{new}} = \frac{(Q_{\text{current}} \times \text{WAC}_{\text{current}}) + (Q_{\text{inward}} \times C_{\text{landed}})}{Q_{\text{current}} + Q_{\text{inward}}}$$
- **Negative Stock**: Allowed on POS sales (flagged as `NEGATIVE_STOCK_WARNING` in `stock_alerts`).
- **Landed Cost**: Freight and hamali charges apportioned proportionally across purchase lines before updating WAC.

### Module 3: Customer & Supplier Ledger
- **Party Balances**: Maintained via append-only `ledger_entries`.
- **Payment Allocation**:
  - Auto-allocates oldest unpaid invoices first (FIFO) unless specific bills are chosen.
  - Tracks 4 ageing buckets: `0–30 days`, `31–60 days`, `61–90 days`, `90+ days`.
- **WhatsApp Integration**: Dispatches formatted payment reminders with UPI payment links.
- **Paisa Integrity**: Balance must always match:
  $$\sum \text{Unpaid Invoices} - \text{Unallocated Advances} == \text{party.current_balance}$$

### Module 4: Reports & Dashboard
- **Owner Morning Dashboard**: Loads in $< 1$ second via pre-calculated snapshots refreshed every 5 minutes.
- **Key Metrics**: Today's sales, gross margin estimate, cash in hand, receivables (overdue count), payables due this week, low-stock warnings, and top debtors.
- **GSTR-1 & 3B**: Exportable to Excel/JSON with exact HSN summaries and taxable splits.

### Module 5: AI Business Assistant
- **Strict Architecture**: The LLM **never writes SQL** and **never performs raw arithmetic**.
- **Fixed Tool Calling**:
  - `get_receivables(min_days, min_amount)`
  - `profit_by_product(period, top_n)`
  - `reorder_suggestions(godown_id)`
  - `sales_summary(period, group_by)`
  - `dead_stock(days)`
  - `customer_summary(party_name)`
  - `payables_due(days)`
- **Response Format**: Dual language output (Tamil & English) with tabular cards and direct links to the relevant report.

---

## 5. Coding & Testing Directives for Agents

When generating or modifying code in this repository:
1. **Never use raw floats for currency or inventory**: Use `Decimal` (Python) or integer cents/paise, and `NUMERIC(18, 4)` in SQL.
2. **Never delete posted records**: Invoices, stock movements, and ledger entries cannot be deleted. Implement credit notes or adjustment vouchers instead.
3. **Always write golden-file tests**:
   - GST calculation splits (Intra-state vs Inter-state).
   - Smart unit decomposition (e.g., 963 pcs $\rightarrow$ 9 boxes 63 pcs).
   - Weighted average cost recalculation on purchase with freight.
   - Offline invoice sequence continuity.
