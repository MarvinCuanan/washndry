# Security Test Evidence

Run these tests against the local XAMPP database and attach screenshots of the
resulting application messages and query output.

## Parameterized-login injection test

Use the literal username:

```text
' OR '1'='1
```

Expected result: `Invalid username or password`. The login query uses
`WHERE username=%s`, so the input remains a value rather than changing SQL
syntax. A vulnerable concatenated query would incorrectly authenticate.

## Role authorization test

1. Log in as Viewer and confirm that reports and read-only pages are available.
2. Attempt to add a customer, record a payment, or update an order status.
3. Confirm that the application displays `Access denied` and makes no database
   change.
4. Log in as Staff and confirm operational writes work but Services and Users
   administration are unavailable.
5. Log in as Admin and confirm user and service administration works.

## Sensitive-data test

Inspect the customer table with:

```sql
SELECT contact_no, contact_hash FROM customer LIMIT 1;
```

`contact_no` must appear as binary ciphertext rather than a readable phone
number. The application decrypts it only after authorization, and the
encryption key is stored outside the database.

## Audit test

Create/update a customer, create an order, and record a payment. Verify:

```sql
SELECT user_id, action, table_name, record_id, occurred_at
FROM audit_log ORDER BY audit_id DESC LIMIT 20;
```
