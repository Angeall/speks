"""Business rules — shipping rate calculation."""

from pydantic import BaseModel

from speks import service, stub


class ZoneInfo(BaseModel):
    """Shipping zone lookup result."""

    zone: int  # Shipping zone number (1-8)
    distance_km: int  # Distance between origin and destination
    cross_border: bool  # Whether the shipment crosses a border
    origin_country: str  # Origin country code
    dest_country: str  # Destination country code


class CarrierRate(BaseModel):
    """Carrier rate quote."""

    base_rate: float  # Base shipping rate
    fuel_surcharge: float  # Fuel surcharge amount
    carrier: str  # Carrier name


@service
class ShippingAPI:
    """Carrier shipping API (blackbox)."""

    @stub(mock=ZoneInfo(
        zone=4,
        distance_km=850,
        cross_border=False,
        origin_country="US",
        dest_country="US",
    ))
    def fetch_zone(self, origin_zip: str, dest_zip: str) -> ZoneInfo:
        """Look up shipping zone from origin/destination postal codes."""
        ...

    @stub(mock=CarrierRate(
        base_rate=5.99,
        fuel_surcharge=0.48,
        carrier="FastShip",
    ))
    def fetch_rate(self, zone: int, weight_kg: float, service_level: str) -> CarrierRate:
        """Get a real-time rate quote from the carrier."""
        ...


class ShippingRate(BaseModel):
    """Complete shipping rate breakdown."""

    carrier: str
    service_level: str
    zone: int
    base_rate: float
    fuel_surcharge: float
    weight_surcharge: float
    zone_surcharge: float
    cross_border_fee: float
    total: float


def calculate_shipping_rate(
    origin_zip: str,
    dest_zip: str,
    weight_kg: float,
    service_level: str = "standard",
) -> ShippingRate:
    """Calculate shipping cost for a package.

    Determines the shipping zone, fetches carrier rates,
    and applies weight-based surcharges.

    :param origin_zip: Origin postal code
    :param dest_zip: Destination postal code
    :param weight_kg: Package weight in kilograms
    :param service_level: Delivery speed tier
    :return: Full rate breakdown with all surcharges
    """
    api = ShippingAPI()
    zone_info = api.fetch_zone(origin_zip, dest_zip)
    carrier = api.fetch_rate(zone_info.zone, weight_kg, service_level)

    base = carrier.base_rate
    fuel = carrier.fuel_surcharge

    weight_surcharge = max(0, (weight_kg - 5)) * 1.50
    zone_surcharge = max(0, (zone_info.zone - 3)) * 2.00
    cross_border_fee = 15.00 if zone_info.cross_border else 0.00

    total = round(base + fuel + weight_surcharge + zone_surcharge + cross_border_fee, 2)

    return ShippingRate(
        carrier=carrier.carrier,
        service_level=service_level,
        zone=zone_info.zone,
        base_rate=base,
        fuel_surcharge=fuel,
        weight_surcharge=round(weight_surcharge, 2),
        zone_surcharge=zone_surcharge,
        cross_border_fee=cross_border_fee,
        total=total,
    )


class ShippingComparison(BaseModel):
    """Comparison of all shipping options for a route."""

    origin: str
    destination: str
    weight_kg: float
    options: list[ShippingRate]
    cheapest: str


def compare_shipping_options(origin_zip: str, dest_zip: str, weight_kg: float) -> ShippingComparison:
    """Compare all available shipping options for a route.

    :param origin_zip: Origin postal code
    :param dest_zip: Destination postal code
    :param weight_kg: Package weight in kilograms
    :return: Side-by-side comparison with the cheapest option highlighted
    """
    options = []
    for level in ["standard", "express", "overnight"]:
        rate = calculate_shipping_rate(origin_zip, dest_zip, weight_kg, level)
        options.append(rate)

    return ShippingComparison(
        origin=origin_zip,
        destination=dest_zip,
        weight_kg=weight_kg,
        options=options,
        cheapest=min(options, key=lambda x: x.total).service_level,
    )
