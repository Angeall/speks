"""Business rules — patient insurance eligibility verification."""

from pydantic import BaseModel

from speks import ExternalService, MockErrorResponse, MockResponse, ServiceError


class InsuranceCoverage(BaseModel):
    """Insurance coverage details from the payer."""

    active: bool
    plan: str
    copay: float
    deductible_remaining: float
    out_of_pocket_max: float
    covered_services: list[str]


class PatientRecord(BaseModel):
    """Patient demographics and medical history."""

    patient_id: str
    age: int
    conditions: list[str]
    member_id: str


class FormularyInfo(BaseModel):
    """Medication coverage information."""

    covered: bool
    tier: int
    requires_prior_auth: bool
    generic_available: bool


class VerifyInsuranceCoverage(ExternalService):
    """Real-time eligibility check with the insurance payer (Blackbox)."""

    component_name = "InsurancePayer"

    def execute(self, member_id: str, service_code: str) -> InsuranceCoverage:
        pass  # type: ignore[return-value]

    def mock(self, member_id: str, service_code: str) -> MockResponse:
        return MockResponse(data=InsuranceCoverage(
            active=True,
            plan="PPO Gold",
            copay=25.0,
            deductible_remaining=500.0,
            out_of_pocket_max=3000.0,
            covered_services=["preventive", "diagnostic", "surgical"],
        ))

    def mock_error(self, member_id: str, service_code: str) -> MockErrorResponse:
        return MockErrorResponse(
            error_code="MEMBER_NOT_FOUND",
            error_message="Member ID not found in payer system.",
            http_code=404,
        )


class FetchPatientRecord(ExternalService):
    """Retrieve patient demographics and medical history (Blackbox)."""

    component_name = "EHR"

    def execute(self, patient_id: str) -> PatientRecord:
        pass  # type: ignore[return-value]

    def mock(self, patient_id: str) -> MockResponse:
        return MockResponse(data=PatientRecord(
            patient_id=patient_id,
            age=45,
            conditions=["hypertension", "diabetes_type2"],
            member_id="INS-001234",
        ))


class CheckFormulary(ExternalService):
    """Check whether a medication is covered by the patient's plan (Blackbox)."""

    component_name = "Pharmacy"

    def execute(self, plan_id: str, medication_code: str) -> FormularyInfo:
        pass  # type: ignore[return-value]

    def mock(self, plan_id: str, medication_code: str) -> MockResponse:
        return MockResponse(data=FormularyInfo(
            covered=True,
            tier=2,
            requires_prior_auth=False,
            generic_available=True,
        ))


class EligibilityResult(BaseModel):
    """Eligibility determination for a medical service."""

    eligible: bool
    patient_id: str
    reason: str | None = None
    plan: str | None = None
    copay: float | None = None
    deductible_remaining: float | None = None


def check_eligibility(patient_id: str, service_code: str) -> EligibilityResult:
    """Verify whether a patient is eligible for a specific medical service.

    Retrieves patient record, checks insurance coverage, and returns
    a combined eligibility determination.
    """
    patient = FetchPatientRecord().call(patient_id)

    try:
        coverage = VerifyInsuranceCoverage().call(
            patient.member_id, service_code
        )
    except ServiceError:
        return EligibilityResult(
            eligible=False,
            reason="Unable to verify insurance coverage",
            patient_id=patient_id,
        )

    if not coverage.active:
        return EligibilityResult(
            eligible=False,
            reason="Insurance plan is not active",
            patient_id=patient_id,
        )

    # Map service code to category
    service_category = service_code.split("-")[0] if "-" in service_code else service_code

    if service_category not in coverage.covered_services:
        return EligibilityResult(
            eligible=False,
            reason=f"Service category '{service_category}' is not covered by plan",
            patient_id=patient_id,
            plan=coverage.plan,
        )

    return EligibilityResult(
        eligible=True,
        patient_id=patient_id,
        plan=coverage.plan,
        copay=coverage.copay,
        deductible_remaining=coverage.deductible_remaining,
    )


class CostEstimate(BaseModel):
    """Patient out-of-pocket cost estimate."""

    covered: bool
    reason: str | None = None
    plan: str | None = None
    billed_amount: float | None = None
    deductible_applied: float | None = None
    copay: float | None = None
    patient_responsibility: float
    insurance_pays: float | None = None


def estimate_patient_cost(patient_id: str, service_code: str, billed_amount: float) -> CostEstimate:
    """Estimate the patient's out-of-pocket cost for a service.

    Considers deductible, copay, and plan maximums.
    """
    eligibility = check_eligibility(patient_id, service_code)

    if not eligibility.eligible:
        return CostEstimate(
            covered=False,
            reason=eligibility.reason,
            patient_responsibility=billed_amount,
        )

    deductible = eligibility.deductible_remaining
    copay = eligibility.copay

    if billed_amount <= deductible:
        patient_pays = billed_amount
    else:
        patient_pays = deductible + copay

    return CostEstimate(
        covered=True,
        plan=eligibility.plan,
        billed_amount=billed_amount,
        deductible_applied=min(billed_amount, deductible),
        copay=copay if billed_amount > deductible else 0,
        patient_responsibility=round(patient_pays, 2),
        insurance_pays=round(billed_amount - patient_pays, 2),
    )
