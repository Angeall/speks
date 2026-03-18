# Regulatory Compliance

## Context

Compliance rules verify that the client is not under sanctions and is not a Politically Exposed Person (PEP).

## Compliance Check Dependencies

@[dependencies](src/compliance.py:check_compliance)

## Source Code

@[code](src/compliance.py:check_compliance)

## Full Evaluation (Credit + Compliance)

This function orchestrates all verifications:

@[dependencies](src/compliance.py:full_evaluation)

@[code](src/compliance.py:full_evaluation)

@[playground](src/compliance.py:full_evaluation)
