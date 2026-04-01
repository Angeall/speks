"""Typed business rules using Pydantic models for structured inputs/outputs.

This module demonstrates how Speks can unfold Pydantic model types
in the contract table, showing the internal structure of each field.
"""

from __future__ import annotations

from pydantic import BaseModel

from speks import ServiceError

from .credit import CheckClientBalance, CheckCreditHistory, CreditHistory


class CreditRequest(BaseModel):
    """A structured credit evaluation request."""

    client_id: str  # Unique client identifier
    amount: float  # Requested credit amount
    score_threshold: int = 600  # Minimum credit score required
    include_history: bool = True  # Whether to include credit history check


class FullCreditDecision(BaseModel):
    """The full credit evaluation result."""

    approved: bool  # Whether the credit was approved
    balance: float  # Client's current balance
    history: CreditHistory | None = None  # Credit history, if requested
    reasons: list[str] = []  # Denial reasons, if any


def evaluate_credit_typed(request: CreditRequest) -> FullCreditDecision:
    """Evaluate a credit request using structured types.

    The contract table will show the structure of both types.

    :param request: Structured credit evaluation request
    :return: Full decision with approval status and details
    """
    try:
        result = CheckClientBalance().call(request.client_id)
    except ServiceError:
        return FullCreditDecision(
            approved=False,
            balance=0.0,
            reasons=["Unable to verify balance"],
        )

    if result.balance <= request.amount:
        return FullCreditDecision(
            approved=False,
            balance=result.balance,
            reasons=["Insufficient balance"],
        )

    if not request.include_history:
        return FullCreditDecision(approved=True, balance=result.balance)

    history = CheckCreditHistory().call(request.client_id)

    score_ok = history.score >= request.score_threshold
    incidents_ok = history.incidents == 0

    reasons = [
        r for r in [
            "Credit score too low" if not score_ok else None,
            "Incidents detected" if not incidents_ok else None,
        ]
        if r
    ]

    return FullCreditDecision(
        approved=score_ok and incidents_ok,
        balance=result.balance,
        history=history,
        reasons=reasons if reasons else [],
    )
