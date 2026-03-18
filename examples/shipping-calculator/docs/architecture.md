# System Architecture

## Full Dependency Map

@[dependencies](src/)

## Focus: Delivery Estimation

@[dependencies](src/delivery.py:estimate_delivery)

## Focus: Rate Comparison

@[dependencies](src/rates.py:compare_shipping_options)

## Rate Calculation Flow

@[mermaid](diagrams/rate-calculation.mmd)

## Delivery Sequence

@[plantuml](diagrams/shipping-flow.puml)

## External Services

### Geo Service

@[code](src/rates.py:FetchZoneMapping)

### Carrier API

@[code](src/rates.py:FetchCarrierRates)

### Warehouse

@[code](src/delivery.py:CheckWarehouseStock)

### Customs API

@[code](src/delivery.py:CheckCustomsClearance)
