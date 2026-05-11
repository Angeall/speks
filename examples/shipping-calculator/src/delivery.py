"""Business rules — delivery time estimation."""

from pydantic import BaseModel

from speks import ServiceError, service, stub

from .rates import ShippingAPI


class WarehouseStock(BaseModel):
    """Stock availability at a warehouse."""

    in_stock: bool
    warehouse_zip: str
    processing_days: int


class CustomsClearance(BaseModel):
    """Customs processing estimate."""

    clearance_days: int
    duties_applicable: bool
    restricted: bool


@service
class LogisticsAPI:
    """Logistics and customs API (blackbox)."""

    @stub(mock=WarehouseStock(
        in_stock=True,
        warehouse_zip="10001",
        processing_days=1,
    ))
    def check_warehouse_stock(self, product_id: str, dest_zip: str) -> WarehouseStock:
        """Check stock availability at the nearest warehouse."""
        ...

    @stub(mock=CustomsClearance(
        clearance_days=0,
        duties_applicable=False,
        restricted=False,
    ))
    def check_customs(self, origin_country: str, dest_country: str, value_usd: float) -> CustomsClearance:
        """Estimate customs processing time for an international shipment."""
        ...


class DeliveryEstimate(BaseModel):
    """Delivery time estimation result."""

    deliverable: bool
    reason: str | None = None
    processing_days: int | None = None
    transit_days: int | None = None
    customs_days: int | None = None
    total_business_days: int | None = None
    service_level: str | None = None
    shipping_from: str | None = None


def estimate_delivery(
    product_id: str,
    dest_zip: str,
    service_level: str = "standard",
    order_value_usd: float = 50.0,
) -> DeliveryEstimate:
    """Estimate delivery date for a product to a destination.

    Considers warehouse processing, transit time (based on zone and service),
    and customs clearance for international orders.
    """
    logistics = LogisticsAPI()
    stock = logistics.check_warehouse_stock(product_id, dest_zip)

    if not stock.in_stock:
        return DeliveryEstimate(
            deliverable=False,
            reason="Product not in stock at any nearby warehouse",
        )

    zone_info = ShippingAPI().fetch_zone(stock.warehouse_zip, dest_zip)

    transit_table = {
        "standard": {1: 3, 2: 4, 3: 5, 4: 6, 5: 7},
        "express": {1: 1, 2: 2, 3: 2, 4: 3, 5: 3},
        "overnight": {1: 1, 2: 1, 3: 1, 4: 1, 5: 2},
    }
    zone = min(zone_info.zone, 5)
    transit_days = transit_table.get(service_level, transit_table["standard"]).get(zone, 7)

    customs_days = 0
    if zone_info.cross_border:
        try:
            customs = logistics.check_customs(
                zone_info.origin_country,
                zone_info.dest_country,
                order_value_usd,
            )
            if customs.restricted:
                return DeliveryEstimate(
                    deliverable=False,
                    reason="Product is restricted for this destination country",
                )
            customs_days = customs.clearance_days
        except ServiceError:
            customs_days = 5

    total_days = stock.processing_days + transit_days + customs_days

    return DeliveryEstimate(
        deliverable=True,
        processing_days=stock.processing_days,
        transit_days=transit_days,
        customs_days=customs_days,
        total_business_days=total_days,
        service_level=service_level,
        shipping_from=stock.warehouse_zip,
    )
