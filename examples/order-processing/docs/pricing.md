# Pricing Rules

## Line Item Pricing

Each product line applies volume-based discounts:

| Quantity | Discount |
|----------|----------|
| 1–9 | 0% |
| 10–49 | 5% |
| 50–99 | 10% |
| 100+ | 15% |

### Contract

@[contract](src/pricing.py:calculate_line_price)

### Source Code

@[code](src/pricing.py:calculate_line_price)

### Try it Live

@[playground](src/pricing.py:calculate_line_price)

---

## Order Total with Loyalty Discount

After computing line totals, the customer's loyalty tier discount is applied.

### Contract

@[contract](src/pricing.py:calculate_order_total)

### Execution Flow

@[sequence](src/pricing.py:calculate_order_total)

### Source Code

@[code](src/pricing.py:calculate_order_total)

### Try it Live

@[playground](src/pricing.py:calculate_order_total)
