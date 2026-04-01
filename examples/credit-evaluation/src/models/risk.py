"""Risk assessment result model."""

from pydantic import BaseModel


class RiskAssessment(BaseModel):
    """Computed risk assessment for a credit request."""

    risk_level: str  # LOW, MEDIUM, HIGH
    score: float  # Numeric risk score (0-100)
    approved: bool  # Final decision
    max_amount: float  # Maximum approved amount
    reasons: list[str] = []  # Explanation factors
