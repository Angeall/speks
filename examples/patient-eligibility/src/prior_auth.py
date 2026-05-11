"""Business rules — prior authorization workflow."""

from pydantic import BaseModel

from speks import service, stub

from .eligibility import EHR, InsurancePayer


class PriorAuthApproval(BaseModel):
    """Prior authorization response from the payer."""

    auth_id: str
    status: str
    valid_from: str
    valid_until: str
    approved_units: int


class ClinicalGuideline(BaseModel):
    """Clinical necessity assessment result."""

    medically_necessary: bool
    guideline: str
    evidence_level: str
    notes: str


@service
class PriorAuthSystem:
    """Prior authorization API (blackbox)."""

    @stub(mock=PriorAuthApproval(
        auth_id="PA-2024-78901",
        status="approved",
        valid_from="2024-01-15",
        valid_until="2024-04-15",
        approved_units=12,
    ))
    def submit(self, auth_request: dict) -> PriorAuthApproval:
        """Submit a prior authorization request to the payer."""
        ...


@service
class ClinicalDB:
    """Clinical guidelines database (blackbox)."""

    @stub(mock=ClinicalGuideline(
        medically_necessary=True,
        guideline="AHA-2023-HBP-MGMT",
        evidence_level="A",
        notes="Recommended for patients with uncontrolled hypertension",
    ))
    def check_guidelines(self, procedure_code: str, conditions: list) -> ClinicalGuideline:
        """Check clinical necessity against evidence-based guidelines."""
        ...


class PriorAuthResult(BaseModel):
    """Final prior authorization evaluation result."""

    status: str
    reason: str | None = None
    auth_id: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    approved_units: int | None = None
    clinical_guideline: str | None = None


def evaluate_prior_auth(patient_id: str, procedure_code: str) -> PriorAuthResult:
    """Evaluate whether a procedure requires prior authorization and if so, request it.

    Steps:
    1. Fetch patient record and insurance coverage
    2. Check clinical guidelines for medical necessity
    3. If required, submit prior auth request to payer
    """
    patient = EHR().fetch_patient_record(patient_id)
    coverage = InsurancePayer().verify_coverage(patient.member_id, procedure_code)

    if not coverage.active:
        return PriorAuthResult(
            status="DENIED",
            reason="Insurance not active",
        )

    clinical = ClinicalDB().check_guidelines(procedure_code, patient.conditions)

    if not clinical.medically_necessary:
        return PriorAuthResult(
            status="DENIED",
            reason="Procedure not deemed medically necessary",
            clinical_guideline=clinical.guideline,
        )

    auth_result = PriorAuthSystem().submit({
        "patient_id": patient_id,
        "member_id": patient.member_id,
        "procedure_code": procedure_code,
        "clinical_justification": clinical.guideline,
        "evidence_level": clinical.evidence_level,
    })

    return PriorAuthResult(
        status=auth_result.status.upper(),
        auth_id=auth_result.auth_id,
        valid_from=auth_result.valid_from,
        valid_until=auth_result.valid_until,
        approved_units=auth_result.approved_units,
        clinical_guideline=clinical.guideline,
    )
