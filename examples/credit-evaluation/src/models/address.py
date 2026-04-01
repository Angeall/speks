"""Address model for client location data."""

from pydantic import BaseModel


class Address(BaseModel):
    """Physical address of a client."""

    street: str  # Street name and number
    city: str  # City name
    zip_code: str  # Postal code
    country: str = "FR"  # ISO country code
