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

@[code](src/pricing.py:FetchProductCatalog)

### Customer Service

@[code](src/pricing.py:FetchCustomerTier)

### Warehouse

@[code](src/orders.py:CheckInventory)

### Payment Gateway

@[code](src/orders.py:ProcessPayment)
