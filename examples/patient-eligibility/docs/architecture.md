# System Architecture

## Full Dependency Map

@[dependencies](src/)

## Focus: Prior Authorization Workflow

@[dependencies](src/prior_auth.py:evaluate_prior_auth)

## Focus: Cost Estimation

@[dependencies](src/eligibility.py:estimate_patient_cost)

## Eligibility Decision Flow

@[mermaid](diagrams/eligibility-flow.mmd)

## Prior Authorization Sequence

@[plantuml](diagrams/prior-auth-flow.puml)

## External Services

### EHR (Electronic Health Records)

@[code](src/eligibility.py:FetchPatientRecord)

### Insurance Payer

@[code](src/eligibility.py:VerifyInsuranceCoverage)

### Pharmacy / Formulary

@[code](src/eligibility.py:CheckFormulary)

### Clinical Guidelines

@[code](src/prior_auth.py:CheckClinicalGuidelines)
