# Performance Test Evidence

Run each query before and after the relevant index is present. Save the
`EXPLAIN` output and record the measured execution time in this table.

| Query | Index | Before plan/time | After plan/time |
|---|---|---|---|
| Orders by date | `idx_order_date` | Fill from XAMPP | Fill from XAMPP |
| Payments by date | `idx_payment_date` | Fill from XAMPP | Fill from XAMPP |

```sql
EXPLAIN SELECT * FROM laundry_order
WHERE order_date >= '2026-01-01' AND order_date < '2026-02-01';

EXPLAIN SELECT * FROM payment
WHERE payment_date >= '2026-01-01' AND payment_date < '2026-02-01';
```

Compare `key`, `type`, and estimated `rows`. Use the same data and date range
for both runs. Do not claim a timing improvement until the local results have
been recorded.
