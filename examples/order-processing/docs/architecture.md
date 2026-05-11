# System Architecture

## Full Dependency Map

@[dependencies](src/)

## Focus: Order Processing Pipeline

@[dependencies](src/orders.py:process_order)

## Order Pipeline

@[mermaid](diagrams/order-pipeline.mmd)

## Sequence Diagram

@[plantuml](diagrams/order-flow.puml)

## External Services

### Product Catalog

@[code](src/pricing.py:ProductCatalog)

### Customer Service

@[code](src/pricing.py:CustomerService)

### Warehouse

@[code](src/orders.py:Warehouse)

### Payment Gateway

@[code](src/orders.py:PaymentGateway)
