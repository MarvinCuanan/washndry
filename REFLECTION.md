# Individual Reflection: Data Governance and Ethics

Wash 'n Dry stores customer names, mobile numbers, addresses, laundry orders,
service selections, payment amounts, status history, and staff activity. Some
of these fields are personal data because they identify a customer or reveal
their location and purchasing history. The application needs this information
to contact customers, identify orders, calculate balances, and provide
accountability for staff actions.

The design applies several protections. Passwords are stored as salted
PBKDF2-HMAC-SHA256 hashes rather than plaintext. Customer contact numbers are
stored as authenticated-encryption ciphertext, while a one-way SHA-256 token
supports duplicate detection without searching ciphertext. SQL values use
prepared statements. Admin, Staff, and Viewer permissions are different, and
critical changes are written to `audit_log`. Transactions and row locks protect
payment balances from concurrent updates. Backups must be protected separately
from the encryption key.

If deployed in a real laundry business, the operator should comply with the
Philippine Data Privacy Act of 2012 and related National Privacy Commission
guidance. Customers should receive a privacy notice explaining the purpose of
collection, the categories of data, retention, sharing, and their rights.
Collection should be limited to what is needed for laundry operations.
Customers should not be required to provide unrelated information, and staff
should not browse customer records without a business purpose.

There are ethical risks even when the data is not medical or financial in the
strict sense. An exposed address could create a safety risk. Order history
could reveal household behavior. A dishonest employee could search for a
customer, copy a phone number, or alter a payment. A stolen backup could expose
many customers at once. The business should use least privilege, individual
accounts, strong passwords, account deactivation, audit reviews, encrypted
backups, key rotation planning, and a documented breach-response process.

Data should have a retention schedule. Completed orders and payment records
may need to be retained for accounting, but old contact information should not
be kept indefinitely. Deletion or anonymization requests should be handled
consistently with legal and accounting obligations. The system should also be
tested with realistic but synthetic data during development rather than using
real customer records.

The most important lesson is that security is not only a login screen. It is a
combination of minimizing collection, protecting data at rest and in transit,
limiting access, recording critical actions, testing recovery, and explaining
the system's decisions to the people whose data it holds.
