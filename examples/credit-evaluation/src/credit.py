"""Business rules — credit evaluation."""

from pydantic import BaseModel

from speks import MockError, ServiceError, service, stub


class ClientBalance(BaseModel):
    """Balance information from the Core Banking system."""

    balance: float  # Current account balance
    currency: str = "USD"  # ISO currency code
    account_status: str = "active"  # Account status (active, frozen, closed)


class CreditHistory(BaseModel):
    """Credit history details from the bureau."""

    score: int  # Credit score (300-850)
    incidents: int  # Number of payment incidents
    last_check_date: str = "unknown"  # Date of last credit check


@service
class CoreBanking:
    """Core Banking API (blackbox)."""

    @stub(
        mock=ClientBalance(balance=1500.0, currency="USD", account_status="active"),
        error=MockError(
            "CLIENT_NOT_FOUND",
            "The specified client was not found.",
            http_code=404,
        ),
    )
    def check_balance(self, client_id: str) -> ClientBalance:
        """Fetch the client's current balance."""
        ...  # real HTTP/SQL implementation

    @stub(
        mock=CreditHistory(score=720, incidents=0),
        error=MockError(
            "CREDIT_HISTORY_UNAVAILABLE",
            "Credit history service is unavailable.",
            http_code=503,
        ),
    )
    def check_credit_history(self, client_id: str) -> CreditHistory:
        """Fetch the client's credit bureau history."""
        ...


def evaluate_credit(client_id: str, amount: float) -> bool:
    """Evaluate whether the client can obtain a credit for the requested amount.

    The rule is simple: the client's balance must exceed the requested amount.

    :param client_id: Unique identifier of the client
    :param amount: Requested credit amount
    :return: True if the credit is approved
    """
    try:
        result = CoreBanking().check_balance(client_id)
    except ServiceError:
        return False
    return result.balance > amount


class CreditDecision(BaseModel):
    """Full credit evaluation result."""

    approved: bool  # Whether the credit was approved
    balance: float  # Client's current balance
    score: int | None = None  # Credit score, if available
    incidents: int | None = None  # Number of incidents, if available
    reasons: list[str] = []  # Reasons for denial, if any


def evaluate_credit_advanced(
    client_id: str, amount: float, score_threshold: int = 600,
) -> CreditDecision:
    """Advanced evaluation combining balance and credit score.

    :param client_id: Unique identifier of the client
    :param amount: Requested credit amount
    :param score_threshold: Minimum credit score required for approval
    :return: Structured decision with approval status and details
    """
    bank = CoreBanking()
    result = bank.check_balance(client_id)

    if result.balance > amount:
        history = bank.check_credit_history(client_id)
        score_ok = history.score >= score_threshold
        incidents_ok = history.incidents == 0
        reasons = [
            r for r in [
                "Credit score too low" if not score_ok else None,
                "Incidents detected" if not incidents_ok else None,
            ]
            if r
        ]
        return CreditDecision(
            approved=score_ok and incidents_ok,
            balance=result.balance,
            score=history.score,
            incidents=history.incidents,
            reasons=reasons,
        )
    else:
        return CreditDecision(
            approved=False,
            balance=result.balance,
            reasons=["Insufficient balance"],
        )
