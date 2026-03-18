# Shipping Rates

## Rate Calculation

Shipping rates are determined by zone, weight, and service level.

### Surcharge Rules

| Surcharge | Rule |
|-----------|------|
| Weight | $1.50/kg over 5 kg |
| Zone | $2.00 per zone beyond zone 3 |
| Cross-border | Flat $15.00 fee |
| Fuel | 8% of base rate |

### Contract

@[contract](src/rates.py:calculate_shipping_rate)

### Execution Flow

@[sequence](src/rates.py:calculate_shipping_rate)

### Source Code

@[code](src/rates.py:calculate_shipping_rate)

### Try it Live

@[playground](src/rates.py:calculate_shipping_rate)

---

## Compare Shipping Options

Quickly compare all service levels for a given route.

### Contract

@[contract](src/rates.py:compare_shipping_options)

### Source Code

@[code](src/rates.py:compare_shipping_options)

### Try it Live

@[playground](src/rates.py:compare_shipping_options)
