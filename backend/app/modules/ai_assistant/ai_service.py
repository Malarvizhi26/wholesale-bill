"""AI Business Assistant Service.

Enforces authoritative constraints:
1. Strict Architecture: The LLM never writes SQL and never performs raw arithmetic.
2. Domain calculations are strictly executed by deterministic tools.
3. Outputs bilingual responses (Tamil and English) with tabular cards and direct links.
"""

from decimal import Decimal
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai_assistant import (
    AIDataCardSchema,
    AITableColumnSchema,
    AIActionLinkSchema,
    AIQueryResponseSchema,
    SuggestedQuerySchema,
)
from app.modules.ai_assistant import tools

TWO_PLACES = Decimal("0.01")


def format_inr(val: Any) -> str:
    """Format Decimal or number as INR currency string."""
    try:
        d = Decimal(str(val)).quantize(TWO_PLACES)
        # Indian number formatting: e.g. 1,23,456.78
        s = f"{d:.2f}"
        parts = s.split(".")
        integer_part = parts[0]
        decimal_part = parts[1]
        
        is_negative = integer_part.startswith("-")
        if is_negative:
            integer_part = integer_part[1:]

        if len(integer_part) > 3:
            last_three = integer_part[-3:]
            rest = integer_part[:-3]
            # split rest in groups of 2
            chunks = []
            while len(rest) > 2:
                chunks.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                chunks.insert(0, rest)
            formatted_int = ",".join(chunks) + "," + last_three
        else:
            formatted_int = integer_part

        prefix = "-₹" if is_negative else "₹"
        return f"{prefix}{formatted_int}.{decimal_part}"
    except Exception:
        return f"₹{val}"


class AIAssistantService:

    # -------------------------------------------------------------------------
    # Intent Detection & Routing
    # -------------------------------------------------------------------------
    @staticmethod
    def classify_intent_and_extract_params(query: str) -> Tuple[str, Dict[str, Any]]:
        """Parse query and extract intent and parameters for tool execution."""
        q = query.strip().lower()
        
        # 1. Profit by product
        profit_keywords = [
            "profit", "profitable", "margin", "gross margin", "high margin",
            "most profit", "highest profit", "earnings",
            "லாபம்", "அதிக லாபம்", "லாபகரமான", "லாப விகிதம்", "லாப"
        ]
        if any(kw in q for kw in profit_keywords):
            period = "MONTH"
            if any(w in q for w in ["today", "இன்று", "today's"]):
                period = "TODAY"
            elif any(w in q for w in ["week", "வாரம்", "this week"]):
                period = "WEEK"
            elif any(w in q for w in ["year", "ஆண்டு", "this year"]):
                period = "YEAR"

            top_n = 5
            match = re.search(r"top\s*(\d+)", q)
            if match:
                top_n = int(match.group(1))

            return "profit_by_product", {"period": period, "top_n": top_n}

        # 2. Receivables / Who owes me money
        receivable_keywords = [
            "who owes", "owes me", "owe me", "who owes me money", "receivable", "receivables",
            "debtor", "debtors", "due from", "pending payment", "unpaid bill",
            "credit balance", "credit dues", "outstanding credit", "overdue customer",
            "கடன் பாக்கி", "யார் தர வேண்டும்", "வரவேண்டிய தொகை", "கடன் வைத்திருக்கும்", "யாருக்கு கடன்"
        ]
        if any(kw in q for kw in receivable_keywords):
            min_days = 0
            if "30" in q:
                min_days = 30
            elif "60" in q:
                min_days = 60
            elif "90" in q:
                min_days = 90
            return "get_receivables", {"min_days": min_days, "min_amount": Decimal("0.00")}

        # 3. Reorder suggestions / Low stock
        reorder_keywords = [
            "reorder", "which items should i reorder", "low stock", "out of stock",
            "shortage", "minimum stock", "order items", "what should i order", "stock alert", "deficit",
            "மீண்டும் ஆர்டர்", "சரக்கு குறைவு", "இருப்பு குறைவு", "தீர்ந்துவிட்டது", "ஆர்டர் செய்ய"
        ]
        if any(kw in q for kw in reorder_keywords):
            return "reorder_suggestions", {"godown_id": None}

        # 4. Sales summary
        sales_keywords = [
            "sales today", "today sales", "today's sales", "how much did i sell", "sales summary",
            "daily sales", "revenue today", "total sales", "bill count", "today's billing",
            "இன்றைய விற்பனை", "இன்று எவ்வளவு விற்றது", "விற்பனை அறிக்கை", "இன்றைய வசூல்", "விற்பனை"
        ]
        if any(kw in q for kw in sales_keywords):
            period = "TODAY"
            if any(w in q for w in ["yesterday", "நேற்று"]):
                period = "YESTERDAY"
            elif any(w in q for w in ["week", "வாரம்"]):
                period = "WEEK"
            elif any(w in q for w in ["month", "மாதம்"]):
                period = "MONTH"
            return "sales_summary", {"period": period, "group_by": "MODE"}

        # 5. Dead stock
        dead_stock_keywords = [
            "dead stock", "unsold", "slow moving", "not selling", "inactive product",
            "stagnant", "stagnant stock", "zero sale",
            "தேக்கமடைந்த", "விற்பனையாகாத", "நகராத சரக்கு", "தேக்கம்"
        ]
        if any(kw in q for kw in dead_stock_keywords):
            days = 60
            match = re.search(r"(\d+)\s*(days|day|நாட்கள்)", q)
            if match:
                days = int(match.group(1))
            return "dead_stock", {"days": days}

        # 6. Customer summary
        customer_keywords = [
            "customer summary", "customer balance", "ledger of", "balance of",
            "how much does", "customer", "வாடிக்கையாளர் கணக்கு", "கணக்கு விவரம்"
        ]
        if any(kw in q for kw in customer_keywords) or (("balance" in q or "கணக்கு" in q) and "supplier" not in q and "சப்ளையர்" not in q):
            # Extract customer name if present
            party_name = None
            for pattern in [
                r"balance of\s+([a-zA-Z0-9\s]+)",
                r"summary for\s+([a-zA-Z0-9\s]+)",
                r"how much does\s+([a-zA-Z0-9\s]+)\s+owe",
                r"ledger of\s+([a-zA-Z0-9\s]+)",
                r"customer\s+([a-zA-Z0-9\s]+)",
                r"([a-zA-Z0-9\s]+)\s+balance",
                r"([a-zA-Z0-9\s]+)\s+கணக்கு",
            ]:
                m = re.search(pattern, q, re.IGNORECASE)
                if m:
                    extracted = m.group(1).strip()
                    # Clean common stop words
                    extracted = re.sub(r"\b(is|the|what|how|show|me)\b", "", extracted, flags=re.I).strip()
                    if extracted:
                        party_name = extracted
                        break
            return "customer_summary", {"party_name": party_name}

        # 7. Payables due / Suppliers
        supplier_keywords = [
            "whom do i owe", "whom do i owe money", "supplier", "suppliers", "payables", "pay to supplier",
            "vendor", "vendor dues", "supplier balances", "pending supplier",
            "சப்ளையர்", "கொடுக்க வேண்டிய", "செலுத்த வேண்டிய", "சப்ளையர் பாக்கி"
        ]
        if any(kw in q for kw in supplier_keywords):
            days = 30
            match = re.search(r"(\d+)\s*(days|day|நாட்கள்)", q)
            if match:
                days = int(match.group(1))
            return "payables_due", {"days": days}

        # Fallback: check general keywords or default to help
        return "general_help", {}

    # -------------------------------------------------------------------------
    # Response Formatting per Tool
    # -------------------------------------------------------------------------
    @staticmethod
    def _format_receivables_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        total_rec = format_inr(data["total_receivables"])
        total_ovd = format_inr(data["total_overdue"])
        count = data["debtor_count"]

        answer_en = (
            f"You have {count} customer(s) with outstanding credit totaling {total_rec}. "
            f"Of this, {total_ovd} is strictly overdue beyond permitted credit terms."
        ) if count > 0 else "Great news! There are currently no outstanding customer receivables."

        answer_ta = (
            f"உங்களுக்கு {count} வாடிக்கையாளர்களிடம் இருந்து வரவேண்டிய மொத்தக் கடன் பாக்கி {total_rec}. "
            f"இதில் அனுமதிக்கப்பட்ட தவணைக் காலத்தை தாண்டிய நிலுவைத் தொகை {total_ovd} ஆகும்."
        ) if count > 0 else "வாடிக்கையாளர் கடன் பாக்கி ஏதும் நிலுவையில் இல்லை. அனைத்து கணக்குகளும் சீராக உள்ளன."

        columns = [
            AITableColumnSchema(key="party_name", label_en="Customer Name", label_ta="வாடிக்கையாளர் பெயர்", type="text"),
            AITableColumnSchema(key="phone", label_en="Phone", label_ta="தொலைபேசி", type="text"),
            AITableColumnSchema(key="total_outstanding_fmt", label_en="Balance Due", label_ta="நிலுவைத் தொகை", type="currency"),
            AITableColumnSchema(key="total_overdue_fmt", label_en="Overdue", label_ta="தவணைக் கடந்தவை", type="currency"),
            AITableColumnSchema(key="credit_days", label_en="Credit Days", label_ta="கடன் நாட்கள்", type="number"),
        ]

        rows = []
        for d in data["debtors"]:
            rows.append({
                "party_name": d["party_name"],
                "phone": d["phone"],
                "total_outstanding_fmt": format_inr(d["total_outstanding"]),
                "total_overdue_fmt": format_inr(d["total_overdue"]),
                "credit_days": d["credit_days"],
                "party_id": d["party_id"],
            })

        data_card = AIDataCardSchema(
            title_en="Customer Receivables & Overdue Dues",
            title_ta="வாடிக்கையாளர் கடன் மற்றும் நிலுவைத் தொகை விவரம்",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Total Receivables", "label_ta": "மொத்த பாக்கி", "value": total_rec},
                {"label_en": "Overdue Amount", "label_ta": "தவணை கடந்தவை", "value": total_ovd},
                {"label_en": "Debtors Count", "label_ta": "வாடிக்கையாளர்கள்", "value": str(count)},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="Open Party Credit Ledger",
            label_ta="கடன் கணக்கு பதிவேடு பார்க்க",
            route="/ledger",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="get_receivables",
            tool_called="get_receivables",
            tool_parameters={"min_days": data["min_days_filter"], "min_amount": str(data["min_amount_filter"])},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Which items should I reorder?", label_ta="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?", query="Which items should I reorder?"),
                SuggestedQuerySchema(label_en="Which products made the most profit this month?", label_ta="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?", query="Which products made the most profit this month?"),
                SuggestedQuerySchema(label_en="Whom do I owe money to?", label_ta="சப்ளையர்களுக்கு நான் கொடுக்க வேண்டிய தொகை எவ்வளவு?", query="Whom do I owe money to?"),
            ],
        )

    @staticmethod
    def _format_profit_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        tot_profit = format_inr(data["total_gross_profit"])
        tot_sales = format_inr(data["total_taxable_sales"])
        margin_pct = f"{Decimal(str(data['overall_margin_percent'])):.1f}%"
        top_n = data["top_n"]
        period = data["period"].lower()

        if data["products"]:
            top_prod_name = data["products"][0]["product_name"]
            top_prod_profit = format_inr(data["products"][0]["gross_profit"])
            answer_en = (
                f"For this {period}, your gross profit is {tot_profit} on {tot_sales} sales (Margin: {margin_pct}). "
                f"The highest profit contributor is '{top_prod_name}' with {top_prod_profit} profit."
            )
            answer_ta = (
                f"இந்த {period} காலத்தில், உங்கள் மொத்த லாபம் {tot_profit} (விற்பனை: {tot_sales}, லாப விகிதம்: {margin_pct}). "
                f"அதிக லாபம் ஈட்டித் தந்த முதல் பொருள் '{top_prod_name}' ({top_prod_profit} லாபம்)."
            )
        else:
            answer_en = f"No sales were recorded for this {period} yet. Total gross profit is ₹0.00."
            answer_ta = f"இந்த {period} காலகட்டத்தில் விற்பனை ஏதும் பதிவாகவில்லை. லாபம் ₹0.00."

        columns = [
            AITableColumnSchema(key="product_name", label_en="Product", label_ta="பொருள்", type="text"),
            AITableColumnSchema(key="qty_sold", label_en="Qty Sold", label_ta="விற்ற அளவு", type="number"),
            AITableColumnSchema(key="taxable_sales_fmt", label_en="Sales (₹)", label_ta="விற்பனை (₹)", type="currency"),
            AITableColumnSchema(key="gross_profit_fmt", label_en="Gross Profit", label_ta="மொத்த லாபம்", type="currency"),
            AITableColumnSchema(key="margin_pct_fmt", label_en="Margin %", label_ta="லாப %", type="badge"),
        ]

        rows = []
        for p in data["products"]:
            rows.append({
                "product_name": p["product_name"],
                "qty_sold": f"{Decimal(str(p['quantity_sold'])):.2f} {p['base_unit']}",
                "taxable_sales_fmt": format_inr(p["taxable_sales"]),
                "gross_profit_fmt": format_inr(p["gross_profit"]),
                "margin_pct_fmt": f"{Decimal(str(p['margin_percent'])):.1f}%",
                "product_id": p["product_id"],
            })

        data_card = AIDataCardSchema(
            title_en=f"Top {top_n} Profitable Products ({period.capitalize()})",
            title_ta=f"அதிக லாபம் தந்த முதல் {top_n} பொருட்கள் ({period})",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Gross Profit", "label_ta": "மொத்த லாபம்", "value": tot_profit},
                {"label_en": "Taxable Sales", "label_ta": "விற்பனை", "value": tot_sales},
                {"label_en": "Margin", "label_ta": "லாப விகிதம்", "value": margin_pct},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="View Gross Margin Report",
            label_ta="லாப நஷ்ட அறிக்கை பார்க்க",
            route="/reports?tab=margin",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="profit_by_product",
            tool_called="profit_by_product",
            tool_parameters={"period": data["period"], "top_n": top_n},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                SuggestedQuerySchema(label_en="Which items should I reorder?", label_ta="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?", query="Which items should I reorder?"),
                SuggestedQuerySchema(label_en="How much did I sell today?", label_ta="இன்றைய விற்பனை எவ்வளவு?", query="How much did I sell today?"),
            ],
        )

    @staticmethod
    def _format_reorder_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        total_items = data["total_reorder_items"]
        critical_count = data["critical_items_count"]

        if total_items > 0:
            answer_en = (
                f"There are {total_items} items currently below minimum stock levels. "
                f"{critical_count} item(s) are critically low or out of stock and require immediate purchase."
            )
            answer_ta = (
                f"குறைந்தபட்ச இருப்பு அளவை விடக் குறைவாக {total_items} பொருட்கள் உள்ளன. "
                f"இதில் {critical_count} பொருட்கள் மிகக் குறைவான அல்லது தீர்ந்துவிட்ட நிலையில் உடனடியாக வாங்கப்பட வேண்டும்."
            )
        else:
            answer_en = "All product inventory levels are healthy and above their minimum thresholds."
            answer_ta = "அனைத்து பொருட்களும் குறைந்தபட்ச அளவுக்கு மேல் போதுமான இருப்பில் உள்ளன."

        columns = [
            AITableColumnSchema(key="product_name", label_en="Product Name", label_ta="பொருள் பெயர்", type="text"),
            AITableColumnSchema(key="current_stock_fmt", label_en="Current Stock", label_ta="தற்போதைய இருப்பு", type="text"),
            AITableColumnSchema(key="min_stock_fmt", label_en="Min Level", label_ta="குறைந்தபட்ச அளவு", type="text"),
            AITableColumnSchema(key="suggested_reorder_fmt", label_en="Suggested Reorder", label_ta="பரிந்துரைக்கப்படும் ஆர்டர்", type="text"),
            AITableColumnSchema(key="severity", label_en="Status", label_ta="நிலை", type="badge"),
        ]

        rows = []
        for it in data["items"]:
            rows.append({
                "product_name": it["tamil_name"] if it.get("tamil_name") else it["product_name"],
                "current_stock_fmt": it["display_stock"] or f"{Decimal(str(it['current_stock'])):.2f} {it['base_unit']}",
                "min_stock_fmt": f"{Decimal(str(it['min_stock'])):.2f} {it['base_unit']}",
                "suggested_reorder_fmt": it["display_suggested_reorder"] or f"{Decimal(str(it['suggested_reorder'])):.2f} {it['base_unit']}",
                "severity": it["severity"],
                "product_id": it["product_id"],
            })

        data_card = AIDataCardSchema(
            title_en="Reorder Suggestions & Deficit Stock",
            title_ta="சரக்கு இருப்பு குறைவு & மறுஆர்டர் பரிந்துரைகள்",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Items to Reorder", "label_ta": "ஆர்டர் செய்ய வேண்டியவை", "value": str(total_items)},
                {"label_en": "Critical/Out of Stock", "label_ta": "அவசரத் தேவை", "value": str(critical_count)},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="Open Stock Alerts & Purchase",
            label_ta="சரக்கு எச்சரிக்கை பார்த்து வாங்க",
            route="/inventory?tab=alerts",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="reorder_suggestions",
            tool_called="reorder_suggestions",
            tool_parameters={"godown_id": data["godown_id"]},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                SuggestedQuerySchema(label_en="Which items are dead stock?", label_ta="விற்பனை ஆகாத தேக்கமடைந்த சரக்குகள் எவை?", query="Which items are dead stock?"),
                SuggestedQuerySchema(label_en="Whom do I owe money to?", label_ta="சப்ளையர்களுக்கு கொடுக்க வேண்டிய பாக்கி எவ்வளவு?", query="Whom do I owe money to?"),
            ],
        )

    @staticmethod
    def _format_sales_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        grand_total = format_inr(data["grand_total"])
        invoices_count = data["total_invoices"]
        period = data["period"].lower()

        modes_breakdown = ", ".join([f"{k}: {format_inr(v)}" for k, v in data["sales_by_mode"].items()])

        answer_en = (
            f"Total sales for {period} is {grand_total} across {invoices_count} bill(s). "
            f"Collections: {modes_breakdown if modes_breakdown else 'No payments recorded'}."
        )
        answer_ta = (
            f"{period} காலகட்டத்தின் மொத்த விற்பனை {grand_total} ({invoices_count} பில்கள்). "
            f"வசூல் முறை: {modes_breakdown if modes_breakdown else 'வசூல் ஏதுமில்லை'}."
        )

        columns = [
            AITableColumnSchema(key="metric", label_en="Metric", label_ta="விவரம்", type="text"),
            AITableColumnSchema(key="value", label_en="Amount", label_ta="மதிப்பு", type="text"),
        ]

        rows = [
            {"metric": "Total Invoices", "value": str(invoices_count)},
            {"metric": "Taxable Amount", "value": format_inr(data["taxable_amount"])},
            {"metric": "GST Tax (CGST+SGST+IGST)", "value": format_inr(data["total_tax"])},
            {"metric": "Round Off", "value": format_inr(data["round_off"])},
            {"metric": "Grand Total", "value": grand_total},
        ]
        for mode, amt in data["sales_by_mode"].items():
            rows.append({"metric": f"Collection ({mode})", "value": format_inr(amt)})

        data_card = AIDataCardSchema(
            title_en=f"Sales Summary ({period.capitalize()})",
            title_ta=f"விற்பனை விவரம் ({period})",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Grand Total", "label_ta": "மொத்த விற்பனை", "value": grand_total},
                {"label_en": "Invoices", "label_ta": "பில்கள்", "value": str(invoices_count)},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="View Daily Sales Report",
            label_ta="தினசரி விற்பனை அறிக்கை பார்க்க",
            route="/reports?tab=daily",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="sales_summary",
            tool_called="sales_summary",
            tool_parameters={"period": data["period"]},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Which products made the most profit this month?", label_ta="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?", query="Which products made the most profit this month?"),
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
            ],
        )

    @staticmethod
    def _format_dead_stock_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        blocked_cap = format_inr(data["total_tied_up_capital"])
        count = data["total_dead_stock_items"]
        days = data["days_threshold"]

        if count > 0:
            answer_en = (
                f"Identified {count} dead stock item(s) with no movement for {days}+ days. "
                f"Tied-up working capital in inactive stock is {blocked_cap}."
            )
            answer_ta = (
                f"கடந்த {days} நாட்களுக்கும் மேலாக விற்பனையாகாமல் தேங்கியுள்ள {count} பொருட்கள் கண்டறியப்பட்டுள்ளன. "
                f"இதில் முடங்கியுள்ள மொத்த மூலதன மதிப்பு {blocked_cap} ஆகும்."
            )
        else:
            answer_en = f"No dead stock detected! All active products have moved within the last {days} days."
            answer_ta = f"தேக்கமடைந்த சரக்குகள் ஏதும் இல்லை. அனைத்து பொருட்களும் கடந்த {days} நாட்களில் சுழற்சியில் உள்ளன."

        columns = [
            AITableColumnSchema(key="product_name", label_en="Product Name", label_ta="பொருள் பெயர்", type="text"),
            AITableColumnSchema(key="current_stock_fmt", label_en="Current Stock", label_ta="இருப்பு", type="text"),
            AITableColumnSchema(key="unit_cost_fmt", label_en="Cost / Unit", label_ta="அடக்க விலை", type="currency"),
            AITableColumnSchema(key="tied_up_fmt", label_en="Blocked Capital", label_ta="முடங்கிய மூலதனம்", type="currency"),
            AITableColumnSchema(key="days_inactive", label_en="Days Inactive", label_ta="தேங்கிய நாட்கள்", type="number"),
        ]

        rows = []
        for it in data["items"]:
            rows.append({
                "product_name": it["product_name"],
                "current_stock_fmt": f"{Decimal(str(it['current_stock'])):.2f} {it['base_unit']}",
                "unit_cost_fmt": format_inr(it["unit_cost"]),
                "tied_up_fmt": format_inr(it["tied_up_capital"]),
                "days_inactive": it["days_inactive"],
                "product_id": it["product_id"],
            })

        data_card = AIDataCardSchema(
            title_en=f"Dead Stock Analysis ({days}+ Days Stagnant)",
            title_ta=f"தேக்கமடைந்த சரக்குகள் பகுப்பாய்வு ({days}+ நாட்கள்)",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Blocked Capital", "label_ta": "முடங்கிய மூலதனம்", "value": blocked_cap},
                {"label_en": "Dead Stock Items", "label_ta": "பொருட்கள் எண்ணிக்கை", "value": str(count)},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="View Inventory Valuation",
            label_ta="சரக்கு மதிப்பு அறிக்கை பார்க்க",
            route="/reports?tab=valuation",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="dead_stock",
            tool_called="dead_stock",
            tool_parameters={"days": days},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Which items should I reorder?", label_ta="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?", query="Which items should I reorder?"),
                SuggestedQuerySchema(label_en="Which products made the most profit this month?", label_ta="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?", query="Which products made the most profit this month?"),
            ],
        )

    @staticmethod
    def _format_customer_summary_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        if not data.get("found"):
            return AIQueryResponseSchema(
                query=query,
                detected_intent="customer_summary",
                tool_called="customer_summary",
                tool_parameters={"party_name": data.get("party_name_queried")},
                answer_en=data.get("message_en", "Customer not found."),
                answer_ta=data.get("message_ta", "வாடிக்கையாளர் கிடைக்கவில்லை."),
                data_card=None,
                action_link=AIActionLinkSchema(
                    label_en="Open Customers Ledger",
                    label_ta="வாடிக்கையாளர் பட்டியல் பார்க்க",
                    route="/ledger",
                    action_type="NAVIGATE",
                ),
                raw_data=data,
                suggested_queries=[
                    SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                ],
            )

        name = data["party_name"]
        bal = format_inr(data["current_balance"])
        overdue = format_inr(data["total_overdue"])
        limit = format_inr(data["credit_limit"])
        exceeded = " (CREDIT LIMIT EXCEEDED!)" if data["is_credit_exceeded"] else ""
        exceeded_ta = " (கடன் வரம்பு மீறப்பட்டுள்ளது!)" if data["is_credit_exceeded"] else ""

        answer_en = (
            f"{name}'s current balance is {bal}{exceeded}. Overdue amount: {overdue}. "
            f"Credit Limit: {limit} ({data['credit_days']} days allowed)."
        )
        answer_ta = (
            f"{name} அவர்களின் தற்போதைய கடன் பாக்கி {bal}{exceeded_ta}. தவணை கடந்த தொகை: {overdue}. "
            f"கடன் வரம்பு: {limit} ({data['credit_days']} நாட்கள் அனுமதிக்கப்பட்டது)."
        )

        columns = [
            AITableColumnSchema(key="category", label_en="Ageing Bucket", label_ta="தவணைக் காலம்", type="text"),
            AITableColumnSchema(key="amount_fmt", label_en="Amount Due", label_ta="நிலுவைத் தொகை", type="currency"),
        ]

        rows = [
            {"category": "0 - 30 Days", "amount_fmt": format_inr(data["bucket_0_30"])},
            {"category": "31 - 60 Days", "amount_fmt": format_inr(data["bucket_31_60"])},
            {"category": "61 - 90 Days", "amount_fmt": format_inr(data["bucket_61_90"])},
            {"category": "90+ Days", "amount_fmt": format_inr(data["bucket_90_plus"])},
            {"category": "Total Overdue", "amount_fmt": overdue},
            {"category": "Current Net Balance", "amount_fmt": bal},
        ]

        data_card = AIDataCardSchema(
            title_en=f"Credit Profile & Ageing: {name}",
            title_ta=f"கடன் விவரம் & தவணைக் கணக்கு: {name}",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Net Balance", "label_ta": "கடன் பாக்கி", "value": bal},
                {"label_en": "Overdue", "label_ta": "தவணை தாண்டியது", "value": overdue},
                {"label_en": "Credit Limit", "label_ta": "கடன் வரம்பு", "value": limit},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en=f"Open {name}'s Ledger",
            label_ta=f"{name} அவர்களின் கணக்கு பதிவேடு பார்க்க",
            route=f"/ledger?party_id={data['party_id']}",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="customer_summary",
            tool_called="customer_summary",
            tool_parameters={"party_id": data["party_id"]},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                SuggestedQuerySchema(label_en="Whom do I owe money to?", label_ta="சப்ளையர்களுக்கு கொடுக்க வேண்டிய பாக்கி எவ்வளவு?", query="Whom do I owe money to?"),
            ],
        )

    @staticmethod
    def _format_payables_response(query: str, data: Dict[str, Any]) -> AIQueryResponseSchema:
        tot_payable = format_inr(data["total_net_payable"])
        count = data["supplier_count"]

        if count > 0:
            top_supplier = data["suppliers"][0]["name"]
            top_amount = format_inr(data["suppliers"][0]["net_payable"])
            answer_en = (
                f"You owe a total of {tot_payable} across {count} supplier(s). "
                f"Largest pending payable is to '{top_supplier}' for {top_amount}."
            )
            answer_ta = (
                f"நீங்கள் {count} சப்ளையர்களுக்கு செலுத்த வேண்டிய மொத்த பாக்கித் தொகை {tot_payable}. "
                f"இதில் அதிகபட்சமாக '{top_supplier}' அவர்களுக்கு {top_amount} செலுத்த வேண்டும்."
            )
        else:
            answer_en = "You have cleared all supplier bills! Total payables are ₹0.00."
            answer_ta = "சப்ளையர் பாக்கி ஏதும் நிலுவையில் இல்லை! செலுத்த வேண்டிய தொகை ₹0.00."

        columns = [
            AITableColumnSchema(key="name", label_en="Supplier Name", label_ta="சப்ளையர் பெயர்", type="text"),
            AITableColumnSchema(key="phone", label_en="Phone", label_ta="தொலைபேசி", type="text"),
            AITableColumnSchema(key="net_payable_fmt", label_en="Payable Due (₹)", label_ta="செலுத்த வேண்டிய பாக்கி", type="currency"),
            AITableColumnSchema(key="total_purchases_fmt", label_en="Total Purchases", label_ta="மொத்த கொள்முதல்", type="currency"),
            AITableColumnSchema(key="last_transaction_date", label_en="Last Transaction", label_ta="கடைசி பரிவர்த்தனை", type="text"),
        ]

        rows = []
        for s in data["suppliers"]:
            rows.append({
                "name": s["name"],
                "phone": s["phone"],
                "net_payable_fmt": format_inr(s["net_payable"]),
                "total_purchases_fmt": format_inr(s["total_purchases"]),
                "last_transaction_date": s["last_transaction_date"],
                "supplier_id": s["supplier_id"],
            })

        data_card = AIDataCardSchema(
            title_en="Pending Supplier Payables",
            title_ta="செலுத்த வேண்டிய சப்ளையர் பாக்கிகள்",
            columns=columns,
            rows=rows,
            summary_chips=[
                {"label_en": "Total Payables", "label_ta": "மொத்த பாக்கி", "value": tot_payable},
                {"label_en": "Suppliers Count", "label_ta": "சப்ளையர்கள்", "value": str(count)},
            ],
        )

        action_link = AIActionLinkSchema(
            label_en="View Supplier Ledger & Pay",
            label_ta="சப்ளையர் கணக்கு பார்க்க & பணம் செலுத்த",
            route="/ledger?tab=suppliers",
            action_type="NAVIGATE",
        )

        return AIQueryResponseSchema(
            query=query,
            detected_intent="payables_due",
            tool_called="payables_due",
            tool_parameters={"days": data["days_filter"]},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=data_card,
            action_link=action_link,
            raw_data=data,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                SuggestedQuerySchema(label_en="Which items should I reorder?", label_ta="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?", query="Which items should I reorder?"),
                SuggestedQuerySchema(label_en="Which products made the most profit this month?", label_ta="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?", query="Which products made the most profit this month?"),
            ],
        )

    @staticmethod
    def _format_help_response(query: str) -> AIQueryResponseSchema:
        answer_en = (
            "வணக்கம்! I am your Hardware Business Assistant. Ask me questions such as:\n"
            "• 'Which products made the most profit this month?'\n"
            "• 'Who owes me money?'\n"
            "• 'Which items should I reorder?'\n"
            "• 'How much did I sell today?'\n"
            "• 'Which items are dead stock?'\n"
            "• 'Whom do I owe money to?'"
        )
        answer_ta = (
            "வணக்கம்! நான் உங்கள் ஹார்டுவேர் கடை உதவியாளர் (AI Business Assistant). நீங்கள் கேட்கக்கூடிய கேள்விகள்:\n"
            "• 'இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?'\n"
            "• 'யாருக்கு கடன் பாக்கி உள்ளது?'\n"
            "• 'எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?'\n"
            "• 'இன்றைய விற்பனை எவ்வளவு?'\n"
            "• 'விற்பனை ஆகாத தேக்கமடைந்த சரக்குகள் எவை?'\n"
            "• 'சப்ளையர்களுக்கு நான் கொடுக்க வேண்டிய தொகை எவ்வளவு?'"
        )
        return AIQueryResponseSchema(
            query=query,
            detected_intent="general_help",
            tool_called="none",
            tool_parameters={},
            answer_en=answer_en,
            answer_ta=answer_ta,
            data_card=None,
            action_link=None,
            suggested_queries=[
                SuggestedQuerySchema(label_en="Which products made the most profit this month?", label_ta="இந்த மாதம் அதிக லாபம் தந்த பொருட்கள் எவை?", query="Which products made the most profit this month?"),
                SuggestedQuerySchema(label_en="Who owes me money?", label_ta="யாருக்கு கடன் பாக்கி உள்ளது?", query="Who owes me money?"),
                SuggestedQuerySchema(label_en="Which items should I reorder?", label_ta="எந்த பொருட்களை மீண்டும் ஆர்டர் செய்ய வேண்டும்?", query="Which items should I reorder?"),
                SuggestedQuerySchema(label_en="How much did I sell today?", label_ta="இன்றைய விற்பனை எவ்வளவு?", query="How much did I sell today?"),
            ],
        )

    # -------------------------------------------------------------------------
    # Main Query Handler
    # -------------------------------------------------------------------------
    @staticmethod
    async def process_query(
        session: AsyncSession,
        tenant_id: str,
        query: str,
        language: str = "both",
    ) -> AIQueryResponseSchema:
        """Classify query, dispatch strictly to domain tool, and format bilingual card response."""
        intent, params = AIAssistantService.classify_intent_and_extract_params(query)

        if intent == "profit_by_product":
            data = await tools.profit_by_product(
                session=session,
                tenant_id=tenant_id,
                period=params.get("period", "MONTH"),
                top_n=params.get("top_n", 5),
            )
            return AIAssistantService._format_profit_response(query, data)

        elif intent == "get_receivables":
            data = await tools.get_receivables(
                session=session,
                tenant_id=tenant_id,
                min_days=params.get("min_days", 0),
                min_amount=params.get("min_amount", Decimal("0.00")),
            )
            return AIAssistantService._format_receivables_response(query, data)

        elif intent == "reorder_suggestions":
            data = await tools.reorder_suggestions(
                session=session,
                tenant_id=tenant_id,
                godown_id=params.get("godown_id"),
            )
            return AIAssistantService._format_reorder_response(query, data)

        elif intent == "sales_summary":
            data = await tools.sales_summary(
                session=session,
                tenant_id=tenant_id,
                period=params.get("period", "TODAY"),
                group_by=params.get("group_by", "MODE"),
            )
            return AIAssistantService._format_sales_response(query, data)

        elif intent == "dead_stock":
            data = await tools.dead_stock(
                session=session,
                tenant_id=tenant_id,
                days=params.get("days", 60),
            )
            return AIAssistantService._format_dead_stock_response(query, data)

        elif intent == "customer_summary":
            data = await tools.customer_summary(
                session=session,
                tenant_id=tenant_id,
                party_name=params.get("party_name"),
            )
            return AIAssistantService._format_customer_summary_response(query, data)

        elif intent == "payables_due":
            data = await tools.payables_due(
                session=session,
                tenant_id=tenant_id,
                days=params.get("days", 30),
            )
            return AIAssistantService._format_payables_response(query, data)

        else:
            return AIAssistantService._format_help_response(query)
