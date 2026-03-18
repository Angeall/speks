# System Architecture

## Overview

The credit evaluation system relies on several external services and interdependent modules.

### Full Dependency Map

@[dependencies](src/)

### Focus: Full Evaluation

The diagram below shows the call chain triggered by `full_evaluation` — the function that orchestrates credit **and** compliance:

@[dependencies](src/compliance.py:full_evaluation)

### Focus: Advanced Credit Evaluation

@[dependencies](src/credit.py:evaluate_credit_advanced)

## Decision Tree

@[mermaid](diagrams/decision-tree.mmd)

## Sequence Diagram

@[plantuml](diagrams/credit-flow.puml)

## External Services

### Credit

@[code](src/credit.py:CheckClientBalance)

@[code](src/credit.py:CheckCreditHistory)

### Compliance

@[code](src/compliance.py:CheckBlacklist)

@[code](src/compliance.py:CheckPEP)
