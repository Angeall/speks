# Delivery Estimation

## Overview

Delivery time depends on warehouse processing, transit (zone + service level), and customs clearance.

### Transit Time Table

| Zone | Standard | Express | Overnight |
|------|----------|---------|-----------|
| 1 | 3 days | 1 day | 1 day |
| 2 | 4 days | 2 days | 1 day |
| 3 | 5 days | 2 days | 1 day |
| 4 | 6 days | 3 days | 1 day |
| 5 | 7 days | 3 days | 2 days |

## Delivery Estimation

### Contract

@[contract](src/delivery.py:estimate_delivery)

### Execution Flow

@[sequence](src/delivery.py:estimate_delivery)

### Source Code

@[code](src/delivery.py:estimate_delivery)

### Try it Live

@[playground](src/delivery.py:estimate_delivery)

## External Services

### Warehouse Stock Check

@[code](src/delivery.py:CheckWarehouseStock)

### Customs Clearance

@[code](src/delivery.py:CheckCustomsClearance)
