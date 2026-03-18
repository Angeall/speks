# Credit Rules

## Context

This document describes the business rules for credit evaluation in our banking system.

## Simple Evaluation

The basic rule checks whether the client's balance exceeds the requested amount.

### Contract

@[contract](src/credit.py:evaluate_credit)

### Source Code

@[code](src/credit.py:evaluate_credit)

### External Service

@[code](src/credit.py:CheckClientBalance)

### Execution Flow

@[sequence](src/credit.py:evaluate_credit)

### Try it Live

@[playground](src/credit.py:evaluate_credit)

---

## Advanced Evaluation

The advanced rule combines balance and credit score.

### Contract

@[contract](src/credit.py:evaluate_credit_advanced)

### Source Code

@[code](src/credit.py:evaluate_credit_advanced)

### Execution Flow

@[sequence](src/credit.py:evaluate_credit_advanced)

### Try it Live

@[playground](src/credit.py:evaluate_credit_advanced)

---

## Typed Evaluation (with Pydantic/Dataclass models)

This version uses structured types for inputs and outputs. The contract table below lets you **unfold** each type to see its internal structure.

### Contract

@[contract](src/typed_credit.py:evaluate_credit_typed)

### Data Models

@[code](src/typed_credit.py:CreditRequest)

@[code](src/typed_credit.py:CreditHistory)

@[code](src/typed_credit.py:CreditDecision)

### Source Code

@[code](src/typed_credit.py:evaluate_credit_typed)

### Try it Live

@[playground](src/typed_credit.py:evaluate_credit_typed)
