"""Business rules — order validation and processing."""

from pydantic import BaseModel

from speks import MockError, ServiceError, service, stub

from .pricing import OrderTotal, calculate_order_total


class StockInfo(BaseModel):
    """Inventory status for a product."""

    available: bool
    stock: int
    warehouse: str


class PaymentResult(BaseModel):
    """Payment gateway response."""

    status: str
    transaction_id: str
    amount: float


@service
class Warehouse:
    """Warehouse inventory API (blackbox)."""

    @stub(
        mock=StockInfo(available=True, stock=250, warehouse="EU-WEST-1"),
        error=MockError(
            "WAREHOUSE_TIMEOUT",
            "Warehouse service did not respond in time.",
            http_code=504,
        ),
    )
    def check_inventory(self, product_id: str) -> StockInfo:
        """Check product availability."""
        ...


@service
class PaymentGateway:
    """Payment gateway API (blackbox)."""

    @stub(
        mock=PaymentResult(status="captured", transaction_id="txn_abc123", amount=0.0),
        error=MockError(
            "PAYMENT_DECLINED",
            "Card was declined by the issuing bank.",
            http_code=402,
        ),
    )
    def charge(self, payment_data: dict) -> PaymentResult:
        """Submit a payment."""
        ...


class ValidationResult(BaseModel):
    """Order validation result."""

    valid: bool
    reason: str | None = None
    unavailable_items: list[dict] = []
    pricing: OrderTotal | None = None


def validate_order(customer_id: str, items: list) -> ValidationResult:
    """Validate an order before processing.

    Checks inventory for each item and calculates the final price.
    Returns a validation result with availability and pricing details.
    """
    warehouse = Warehouse()
    unavailable = []
    for item in items:
        try:
            stock = warehouse.check_inventory(item["product_id"])
            if not stock.available or stock.stock < item["quantity"]:
                unavailable.append({
                    "product_id": item["product_id"],
                    "requested": item["quantity"],
                    "available": stock.stock,
                })
        except ServiceError:
            unavailable.append({
                "product_id": item["product_id"],
                "requested": item["quantity"],
                "available": 0,
                "error": "Could not verify stock",
            })

    if unavailable:
        return ValidationResult(
            valid=False,
            reason="Some items are unavailable",
            unavailable_items=unavailable,
        )

    pricing = calculate_order_total(customer_id, items)

    return ValidationResult(valid=True, pricing=pricing)


class OrderResult(BaseModel):
    """Final order processing result."""

    status: str
    reason: str | None = None
    transaction_id: str | None = None
    total_charged: float | None = None
    pricing: OrderTotal | None = None
    details: list[dict] = []


def process_order(customer_id: str, items: list, payment_method: str) -> OrderResult:
    """Process a complete order: validate, price, and charge.

    Orchestrates inventory check, pricing, and payment in sequence.
    """
    validation = validate_order(customer_id, items)

    if not validation.valid:
        return OrderResult(
            status="REJECTED",
            reason=validation.reason,
            details=validation.unavailable_items,
        )

    total = validation.pricing.total

    try:
        payment = PaymentGateway().charge({
            "amount": total,
            "method": payment_method,
            "customer_id": customer_id,
        })
    except ServiceError:
        return OrderResult(
            status="PAYMENT_FAILED",
            reason="Payment could not be processed",
        )

    return OrderResult(
        status="CONFIRMED",
        transaction_id=payment.transaction_id,
        total_charged=payment.amount,
        pricing=validation.pricing,
    )
