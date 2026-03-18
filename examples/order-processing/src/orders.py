"""Business rules — order validation and processing."""

from pydantic import BaseModel

from speks import ExternalService, MockErrorResponse, MockResponse, ServiceError

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


class CheckInventory(ExternalService):
    """Check product availability in the warehouse (Blackbox)."""

    component_name = "Warehouse"

    def execute(self, product_id: str) -> StockInfo:
        pass  # type: ignore[return-value]

    def mock(self, product_id: str) -> MockResponse:
        return MockResponse(data=StockInfo(
            available=True,
            stock=250,
            warehouse="EU-WEST-1",
        ))

    def mock_error(self, product_id: str) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="WAREHOUSE_TIMEOUT",
            error_message="Warehouse service did not respond in time.",
            http_code=504,
        )


class ProcessPayment(ExternalService):
    """Submit payment to the payment gateway (Blackbox)."""

    component_name = "PaymentGateway"

    def execute(self, payment_data: dict) -> PaymentResult:
        pass  # type: ignore[return-value]

    def mock(self, payment_data: dict) -> MockResponse:
        return MockResponse(data=PaymentResult(
            status="captured",
            transaction_id="txn_abc123",
            amount=payment_data.get("amount", 0),
        ))

    def mock_error(self, payment_data: dict) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="PAYMENT_DECLINED",
            error_message="Card was declined by the issuing bank.",
            http_code=402,
        )


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
    unavailable = []
    for item in items:
        try:
            stock = CheckInventory().call(item["product_id"])
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
        payment = ProcessPayment().call({
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
