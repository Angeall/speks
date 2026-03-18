"""Business rules — credit evaluation."""

from pydantic import BaseModel

from speks import ExternalService, MockErrorResponse, MockResponse, ServiceError


class ClientBalance(BaseModel):
    """Balance information from the Core Banking system."""

    balance: float
    currency: str = "USD"
    account_status: str = "active"


class CreditHistory(BaseModel):
    """Credit history details from the bureau."""

    score: int
    incidents: int
    last_check_date: str = "unknown"


class CheckClientBalance(ExternalService):
    """Call to the Core Banking API (Blackbox)."""

    component_name = "CoreBanking"

    def execute(self, client_id: str) -> ClientBalance:
        pass  # type: ignore[return-value]

    def mock(self, client_id: str) -> MockResponse:
        return MockResponse(data=ClientBalance(
            balance=1500.0,
            currency="USD",
            account_status="active",
        ))

    def mock_error(self, client_id: str) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="CLIENT_NOT_FOUND",
            error_message="The specified client was not found.",
            http_code=404,
        )


class CheckCreditHistory(ExternalService):
    """Call to the credit history service (Blackbox)."""

    component_name = "CoreBanking"

    def execute(self, client_id: str) -> CreditHistory:
        pass  # type: ignore[return-value]

    def mock(self, client_id: str) -> MockResponse:
        return MockResponse(data=CreditHistory(score=720, incidents=0))

    def mock_error(self, client_id: str) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="CREDIT_HISTORY_UNAVAILABLE",
            error_message="Credit history service is unavailable.",
            http_code=503,
        )


def evaluate_credit(client_id: str, amount: float) -> bool:
    """Evaluate whether the client can obtain a credit for the requested amount.

    The rule is simple: the client's balance must exceed the requested amount.
    """
    try:
        result = CheckClientBalance().call(client_id)
    except ServiceError:
        return False
    return result.balance > amount


class CreditDecision(BaseModel):
    """Full credit evaluation result."""

    approved: bool
    balance: float
    score: int | None = None
    incidents: int | None = None
    reasons: list[str] = []


def evaluate_credit_advanced(client_id: str, amount: float, score_threshold: int = 600) -> CreditDecision:
    """Advanced evaluation combining balance and credit score.

    Returns a structured CreditDecision with the decision and details.
    """
    result = CheckClientBalance().call(client_id)

    if result.balance > amount:
        history = CheckCreditHistory().call(client_id)
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
