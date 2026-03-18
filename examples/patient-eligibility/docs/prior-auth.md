# Prior Authorization

## Overview

Some procedures require prior authorization from the insurance payer before they can be performed. This workflow checks clinical necessity and submits the authorization request.

## Prior Auth Evaluation

### Contract

@[contract](src/prior_auth.py:evaluate_prior_auth)

### Execution Flow

@[sequence](src/prior_auth.py:evaluate_prior_auth)

### Source Code

@[code](src/prior_auth.py:evaluate_prior_auth)

### Try it Live

@[playground](src/prior_auth.py:evaluate_prior_auth)

## External Services

### Insurance Payer — Prior Auth Submission

@[code](src/prior_auth.py:SubmitPriorAuth)

### Clinical Guidelines Database

@[code](src/prior_auth.py:CheckClinicalGuidelines)
