"""Compliance rules — regulatory checks."""

from pydantic import BaseModel

from speks import service, stub

from .credit import evaluate_credit


class PEPStatus(BaseModel):
    """Politically Exposed Person check result."""

    is_pep: bool
    level: str | None = None


@service
class ComplianceService:
    """Regulatory compliance API (sanctions + PEP)."""

    @stub(mock=False)
    def check_blacklist(self, client_id: str) -> bool:
        """Check the sanctions blacklist for a client."""
        ...

    @stub(mock=PEPStatus(is_pep=False, level=None))
    def check_pep(self, client_id: str) -> PEPStatus:
        """Look up the Politically Exposed Persons registry."""
        ...


class ComplianceResult(BaseModel):
    """Result of regulatory compliance checks."""

    compliant: bool
    blacklisted: bool
    pep: bool


def check_compliance(client_id: str) -> ComplianceResult:
    """Check whether the client meets regulatory requirements.

    Verifies against the sanctions blacklist and PEP status.
    """
    compliance = ComplianceService()
    on_blacklist = compliance.check_blacklist(client_id)
    pep_info = compliance.check_pep(client_id)

    return ComplianceResult(
        compliant=not on_blacklist and not pep_info.is_pep,
        blacklisted=on_blacklist,
        pep=pep_info.is_pep,
    )


class FullEvaluationResult(BaseModel):
    """Combined credit and compliance evaluation."""

    decision: str
    credit_ok: bool
    compliance: ComplianceResult


def full_evaluation(client_id: str, amount: float) -> FullEvaluationResult:
    """Full evaluation: credit + compliance.

    Combines credit verification and compliance checks
    to produce a final decision.
    """
    credit_ok = evaluate_credit(client_id, amount)
    compliance = check_compliance(client_id)

    return FullEvaluationResult(
        decision="APPROVED" if credit_ok and compliance.compliant else "DENIED",
        credit_ok=credit_ok,
        compliance=compliance,
    )
