"""Business rules — pricing and discounts."""

from pydantic import BaseModel

from speks import service, stub


class ProductInfo(BaseModel):
    """Product details from the catalog."""

    id: str
    name: str
    base_price: float
    category: str


class CustomerTier(BaseModel):
    """Customer loyalty tier information."""

    tier: str
    discount_pct: int
    member_since: str


@service
class ProductCatalog:
    """Product catalog API (blackbox)."""

    @stub(mock=ProductInfo(
        id="p1",
        name="Wireless Headphones",
        base_price=79.99,
        category="electronics",
    ))
    def fetch_product(self, product_id: str) -> ProductInfo:
        """Retrieve product details from the catalog."""
        ...


@service
class CustomerService:
    """Customer service API (blackbox)."""

    @stub(mock=CustomerTier(
        tier="gold",
        discount_pct=10,
        member_since="2022-03-15",
    ))
    def fetch_tier(self, customer_id: str) -> CustomerTier:
        """Retrieve the customer's loyalty tier."""
        ...


class LinePriceResult(BaseModel):
    """Pricing result for a single order line."""

    product: str
    unit_price: float
    quantity: int
    volume_discount_pct: float
    line_total: float


def calculate_line_price(product_id: str, quantity: int) -> LinePriceResult:
    """Calculate the price for a single order line.

    Fetches the product from the catalog and applies quantity-based pricing.
    """
    product = ProductCatalog().fetch_product(product_id)
    unit_price = product.base_price

    if quantity >= 100:
        discount = 0.15
    elif quantity >= 50:
        discount = 0.10
    elif quantity >= 10:
        discount = 0.05
    else:
        discount = 0.0

    discounted_price = round(unit_price * (1 - discount), 2)

    return LinePriceResult(
        product=product.name,
        unit_price=unit_price,
        quantity=quantity,
        volume_discount_pct=discount * 100,
        line_total=round(discounted_price * quantity, 2),
    )


class OrderTotal(BaseModel):
    """Full order pricing breakdown."""

    customer_tier: str
    lines: list[LinePriceResult]
    subtotal: float
    loyalty_discount_pct: int
    loyalty_savings: float
    total: float


def calculate_order_total(
    customer_id: str,
    items: list,
) -> OrderTotal:
    """Calculate the total price for an order with loyalty discounts.

    Applies volume discounts per line, then the customer's loyalty discount on top.
    """
    customer = CustomerService().fetch_tier(customer_id)
    loyalty_discount = customer.discount_pct / 100

    subtotal = 0.0
    lines = []
    for item in items:
        line = calculate_line_price(item["product_id"], item["quantity"])
        lines.append(line)
        subtotal += line.line_total

    loyalty_savings = round(subtotal * loyalty_discount, 2)
    total = round(subtotal - loyalty_savings, 2)

    return OrderTotal(
        customer_tier=customer.tier,
        lines=lines,
        subtotal=subtotal,
        loyalty_discount_pct=customer.discount_pct,
        loyalty_savings=loyalty_savings,
        total=total,
    )
