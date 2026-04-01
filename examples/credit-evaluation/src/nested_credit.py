"""Premium credit evaluation with deeply nested Pydantic models.

Demonstrates how Speks resolves nested types imported from sub-packages.
The contract table will recursively unfold ClientProfile -> Address and
display the full structure.
"""

from __future__ import annotations

from speks import ServiceError

from .credit import CheckClientBalance
from .models import ClientProfile, RiskAssessment


def evaluate_premium_credit(profile: ClientProfile, amount: float) -> RiskAssessment:
    """Evaluate a premium credit request based on the full client profile.

    Uses nested models: ClientProfile contains an Address, and the function
    returns a RiskAssessment.  All three models appear in the contract table.

    :param profile: Full client profile with address
    :param amount: Requested credit amount
    :return: Detailed risk assessment
    """
    try:
        result = CheckClientBalance().call(profile.client_id)
    except ServiceError:
        return RiskAssessment(
            risk_level="HIGH",
            score=100.0,
            approved=False,
            max_amount=0.0,
            reasons=["Unable to verify balance"],
        )

    balance = result.balance
    ratio = amount / max(balance, 1)

    reasons: list[str] = []
    score = 50.0

    # Income-based adjustment
    if profile.income > 0:
        income_ratio = amount / profile.income
        if income_ratio > 5:
            score += 30
            reasons.append("Amount exceeds 5x annual income")
        elif income_ratio > 3:
            score += 15
            reasons.append("Amount exceeds 3x annual income")

    # Seniority bonus
    if profile.years_as_client >= 5:
        score -= 10
    elif profile.years_as_client >= 2:
        score -= 5

    # Balance coverage
    if ratio > 1:
        score += 20
        reasons.append("Insufficient balance coverage")

    score = max(0, min(100, score))

    if score < 40:
        level = "LOW"
    elif score < 70:
        level = "MEDIUM"
    else:
        level = "HIGH"

    approved = score < 60
    max_approved = balance * 0.8 if approved else 0.0

    return RiskAssessment(
        risk_level=level,
        score=score,
        approved=approved,
        max_amount=max_approved,
        reasons=reasons if reasons else ["All checks passed"],
    )
