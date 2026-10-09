"""Product Master and Unit schemas."""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProductUnitSchema(BaseModel):
    id: Optional[str] = None
    unit_name: str
    conversion_factor: Decimal = Field(gt=0)
    can_buy: bool = True
    can_sell: bool = True
    barcode: Optional[str] = None
    is_default_sales_unit: bool = False
    is_default_purchase_unit: bool = False


class ProductPriceSchema(BaseModel):
    price_list_id: str
    unit_name: str
    price: Decimal = Field(ge=0)
    min_allowed_price: Optional[Decimal] = None


class ProductCreateSchema(BaseModel):
    code: str
    name: str
    tamil_name: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    hsn_code: str
    base_unit: str  # 'piece', 'kg', 'metre', etc.
    is_variable_weight: bool = False
    min_stock_base: Decimal = Decimal("0.0000")
    reorder_quantity_base: Decimal = Decimal("0.0000")
    purchase_price_base: Decimal = Decimal("0.0000")
    units: List[ProductUnitSchema] = []
    prices: List[ProductPriceSchema] = []


class ProductResponseSchema(BaseModel):
    id: str
    code: str
    name: str
    tamil_name: Optional[str] = None
    category_id: Optional[str] = None
    brand_id: Optional[str] = None
    hsn_code: str
    base_unit: str
    is_variable_weight: bool
    min_stock_base: Decimal
    reorder_quantity_base: Decimal
    purchase_price_base: Decimal
    is_active: bool
    units: List[ProductUnitSchema] = []

    model_config = ConfigDict(from_attributes=True)
