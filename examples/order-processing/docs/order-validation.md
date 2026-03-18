# Order Validation & Processing

## Order Validation

Before processing, each order is validated against inventory.

### Contract

@[contract](src/orders.py:validate_order)

### Source Code

@[code](src/orders.py:validate_order)

### Execution Flow

@[sequence](src/orders.py:validate_order)

### Try it Live

@[playground](src/orders.py:validate_order)

---

## Full Order Processing

The complete order flow: validate, price, and charge.

### Contract

@[contract](src/orders.py:process_order)

### Execution Flow

@[sequence](src/orders.py:process_order)

### Source Code

@[code](src/orders.py:process_order)

### Try it Live

@[playground](src/orders.py:process_order)
