"""Client profile model with nested address."""

from pydantic import BaseModel

from .address import Address


class ClientProfile(BaseModel):
    """Full client profile used for premium credit evaluation."""

    client_id: str  # Unique client identifier
    name: str  # Full name
    address: Address  # Client's registered address
    income: float  # Annual income
    years_as_client: int = 0  # Seniority in years
