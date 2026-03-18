"""Business rules — shipping rate calculation."""

from pydantic import BaseModel

from speks import ExternalService, MockResponse


class ZoneInfo(BaseModel):
    """Shipping zone lookup result."""

    zone: int
    distance_km: int
    cross_border: bool
    origin_country: str
    dest_country: str


class CarrierRate(BaseModel):
    """Carrier rate quote."""

    base_rate: float
    fuel_surcharge: float
    carrier: str


class FetchZoneMapping(ExternalService):
    """Look up shipping zone from origin/destination postal codes (Blackbox)."""

    component_name = "GeoService"

    def execute(self, origin_zip: str, dest_zip: str) -> ZoneInfo:
        pass  # type: ignore[return-value]

    def mock(self, origin_zip: str, dest_zip: str) -> MockResponse:
        return MockResponse(data=ZoneInfo(
            zone=4,
            distance_km=850,
            cross_border=False,
            origin_country="US",
            dest_country="US",
        ))


class FetchCarrierRates(ExternalService):
    """Get real-time rates from carrier API (Blackbox)."""

    component_name = "CarrierAPI"

    def execute(self, zone: int, weight_kg: float, service_level: str) -> CarrierRate:
        pass  # type: ignore[return-value]

    def mock(self, zone: int, weight_kg: float, service_level: str) -> MockResponse:
        base_rates = {"standard": 5.99, "express": 12.99, "overnight": 24.99}
        base = base_rates.get(service_level, 9.99)
        return MockResponse(data=CarrierRate(
            base_rate=base,
            fuel_surcharge=round(base * 0.08, 2),
            carrier="FastShip",
        ))


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
    """
    zone_info = FetchZoneMapping().call(origin_zip, dest_zip)
    carrier = FetchCarrierRates().call(zone_info.zone, weight_kg, service_level)

    base = carrier.base_rate
    fuel = carrier.fuel_surcharge

    # Weight surcharge: $1.50 per kg over 5kg
    weight_surcharge = max(0, (weight_kg - 5)) * 1.50

    # Zone surcharge: $2 per zone beyond zone 3
    zone_surcharge = max(0, (zone_info.zone - 3)) * 2.00

    # Cross-border fee
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

    Returns pricing for standard, express, and overnight delivery.
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
