# Uniday-support

A Flask and MongoDB application for securely managing university student support requests.

## Local verification demo

Use Python 3.12 or newer with the dependencies in `requirements.txt`. Start the
MongoDB and Mailpit containers with `docker compose up -d`, and run the app with
`flask --app 'app:create_app' run`. Open it at http://127.0.0.1:5000; on some
Macs `localhost` resolves to an IPv6 service that also uses port 5000. The local `.env` holds independent application
and registry credentials, a session secret, and the configured `BASE_URL`; see
`.env.example` for the required variable names. Never commit real credentials.

For a local demonstration, `data/examples/student_registry.example.csv` contains
synthetic records. Validate CSV or JSON with `python -m scripts.seed_registry FILE`;
this is a dry run (also available with `--dry-run`). `--apply` requires
`REGISTRY_SEED_URI` in the environment or local `.env` to point to a separate
import identity with find, insert and createIndex on the registry collection.
Exact existing records are skipped without changing their claim state; conflicting
records stop the import. An interrupted standalone MongoDB bulk insert can be
partial; rerun the command to safely skip matching records. The web registry identity has only find/update access;
it cannot insert new trusted records. Real datasets can contain personal data:
use fabricated or consistently pseudonymised records for development and never
commit raw registry data. MongoDB privileges are collection-level: an identity
allowed to update claims can also modify other fields in that collection.

The signup form remains unchanged. A matching ID and email triggers a message
to Mailpit at http://127.0.0.1:8025. The recipient opens the link and chooses a
**new final password**, preventing the person who initiated signup from choosing
the active account's credential. Links expire after 30 minutes; reissue is limited
to once per minute per pending account. GET does not activate an account; a
CSRF-protected POST is required. Mailpit accepts and displays all local messages;
it does not establish ownership of a real mailbox and must not be internet-facing.

## Security limitations

Student requests now save to the local `cases_db` using the separate `CASES_URI`
identity. Student reads and replies are scoped to the signed-in owner; staff
can claim unassigned requests and access only their assigned cases. Admin pages
show local case counts, user records and audit events. Use synthetic information only: this is
not a live support service and is not suitable for emergencies or real sensitive records.
Staff updates use conditional version checks; cases predating this feature are
treated as version zero until their next update. Archive hides a retained case
from both staff and student pages. Reassignment checks the target staff account
before the case write, but a target could be deactivated between those operations
on standalone MongoDB. Restart all application processes after an upgrade so an
older process cannot bypass version checks. Audit events are best effort and are
not atomic with case changes.
Local MongoDB storage is not configured for encryption at rest. For a fresh
installation, provision `cases_app` with `readWrite` only on `cases_db`, set
`CASES_URI` in the ignored `.env`, and keep the password out of source control.

The registry is only as trustworthy and current as its source. Its ID/email
match is not independent proof of identity; real deployments need authoritative
student records and institutional email or SSO. In-memory limits reset on
restart and are not shared between workers. Signup hashes passwords for both
matched and unmatched inputs, but synchronous database and SMTP work can still
produce observable timing differences. MongoDB runs as a standalone server;
registry claims and account creation span documents without transactions. A
process crash between the claim and insert can strand a claim and requires
administrator reconciliation. The email confirmation uses an atomic update of
the user document to enforce single use even if token bookkeeping fails.
Flask's default client-side signed sessions are not independently revocable
after logout; a stolen previously issued cookie could be replayed until expiry.
Use a revocable server-side session mechanism before production. Audit delivery
is best effort, so a database outage can cause missing audit events. No real email
verification or privacy compliance is established by the local demo.

## Test and security checks

Run `python -m pytest -q` for unit tests. Integration tests require an explicitly
configured `TEST_MONGODB_URI` with permission to create and remove throwaway
`unidays_test_*` databases. Set `TEST_MAILPIT=1` to include the local SMTP test.
Never point the test setting at a server that must not create/delete test data.
Run `python -m bandit -r app.py db.py services scripts` and
`python -m pip_audit -r requirements.txt` for security checks.

| Test | Requirement | STRIDE category | Result |
| --- | --- | --- | --- |
| Registry mismatch and concurrent claim | Match trusted records; one claimant | Spoofing, Tampering | Passed |
| Verification GET, POST, expiry, tampering and replay | Valid, single-use token | Spoofing, Tampering | Passed |
| Initial password rejected after verification | Mailbox holder chooses final password | Spoofing | Passed |
| Inactive sign-in, resend cooldown and IP limit | Prevent unverified access and abuse | Spoofing, Denial of Service | Passed |
| SMTP failure | Keep account inactive on failed delivery | Tampering | Passed |
| Missing CSRF token and POST-only logout | Protect state-changing requests | Tampering | Passed |
| Registry operator input rejection | Reject non-string query inputs | Tampering | Passed |

These results reflect the local run with MongoDB and Mailpit. Audit event writing
is exercised during integration tests, but failure handling and event completeness
need further dedicated tests before claiming full repudiation protection.
