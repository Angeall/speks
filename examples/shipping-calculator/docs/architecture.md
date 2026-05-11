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

### Shipping API

@[code](src/rates.py:ShippingAPI)

### Logistics API

@[code](src/delivery.py:LogisticsAPI)
