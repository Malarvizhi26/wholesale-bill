"""Pydantic V2 Schemas for AI Business Assistant."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AIQueryRequestSchema(BaseModel):
    query: str = Field(..., description="User question in English or Tamil")
    tenant_id: Optional[str] = Field(None, description="Optional tenant UUID")
    language: Optional[str] = Field("both", description="'en', 'ta', or 'both'")


class AITableColumnSchema(BaseModel):
    key: str
    label_en: str
    label_ta: str
    type: str = "text"  # "text", "currency", "number", "badge"


class AIDataCardSchema(BaseModel):
    title_en: str
    title_ta: str
    columns: List[AITableColumnSchema] = []
    rows: List[Dict[str, Any]] = []
    summary_chips: List[Dict[str, Any]] = []


class AIActionLinkSchema(BaseModel):
    label_en: str
    label_ta: str
    route: str
    action_type: str = "NAVIGATE"
    metadata: Dict[str, Any] = {}


class SuggestedQuerySchema(BaseModel):
    label_en: str
    label_ta: str
    query: str


class AIQueryResponseSchema(BaseModel):
    query: str
    detected_intent: str
    tool_called: str
    tool_parameters: Dict[str, Any] = {}
    answer_en: str
    answer_ta: str
    data_card: Optional[AIDataCardSchema] = None
    action_link: Optional[AIActionLinkSchema] = None
    raw_data: Optional[Dict[str, Any]] = None
    suggested_queries: List[SuggestedQuerySchema] = []
