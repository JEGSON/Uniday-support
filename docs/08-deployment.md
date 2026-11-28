# 08 — Isolated local HTTPS deployment

This is a development demonstration with fictional data. It is not a production
deployment or monitored support service. It uses the separate Compose project
`unidays-stage7` and a separate MongoDB volume. Existing local accounts, registry
records and cases are not copied. `--profile dev` enables Mailpit; the stack is
intentionally unsuitable for real email delivery.

## Components and boundaries

- nginx listens only on `127.0.0.1:5443` and terminates HTTPS using a local self-signed
  certificate; the browser will warn until the certificate is explicitly trusted.
- The Flask image runs as UID 10001, with a read-only root filesystem and dropped
  capabilities. Gunicorn uses one worker because rate limits are held in memory.
- MongoDB has authentication enabled, no published host port, a separate named volume,
  and first-run users created by `deploy/mongo-init.js`. The auth and case accounts
  have database-wide `readWrite`; registry claim, statistics, and audit identities use
  narrower roles. `find` on the case collection still permits reading whole documents;
  the statistics service itself returns only aggregates.
- Mailpit is a development-only profile, exposed only on `127.0.0.1:18025`. The app
  sends to it on the internal network; no real email is delivered.
- Compose gives each service a health check. The app health check proves the landing
  page responds; it is **not** a complete database or signup readiness check.

nginx and Mailpit also join a frontend network so their localhost-bound ports can be
published; MongoDB and Flask join only the internal backend network. The nginx proxy
overwrites forwarded address and scheme headers. The app trusts one
proxy only when `TRUST_PROXY=1`; do not expose the app container directly or set that
flag without an equivalent trusted proxy/network arrangement. All service traffic
inside this local network is unencrypted; TLS applies between browser and nginx only.
nginx suppresses the application's HSTS header for this localhost-only demo to avoid
altering browser behaviour for other local projects; a real HTTPS deployment needs its
own carefully reviewed HSTS policy.

## First-time setup

From the project root, activate the existing Python environment and run:

```bash
python -m scripts.prepare_deployment
mkdir -p deploy/certs
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 \
  -keyout deploy/certs/localhost.key -out deploy/certs/localhost.crt \
  -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1'
docker compose -p unidays-stage7 --profile dev -f compose.deploy.yaml up -d --build
```

The secret generator refuses to overwrite existing deployment environment files. It
creates `.env.deploy.mongo`, `.env.deploy.app` and `.env.deploy.importer` with owner-only permissions; these
files and the private key are ignored by Git. Store the encryption key in an
independently protected backup; losing it makes encrypted records unreadable. Do not
paste secrets or print expanded Compose configuration. To regenerate a certificate,
first decide what to do with the existing private key; do not overwrite it blindly.
If the secret generator fails after writing one file, inspect its state before retrying;
it deliberately will not replace a partial setup automatically.

Open `https://localhost:5443` and the Mailpit inbox at `http://127.0.0.1:18025`.
Because this is a self-signed certificate, the browser warning is expected; bypassing
it is appropriate only for this controlled local demo. The dedicated registry starts
empty on a fresh volume. During verification, two bundled fictional records were
imported. No existing user credentials or case records were moved to this new database.

To create a fictional staff account for this isolated deployment:

```bash
docker compose -p unidays-stage7 --profile dev -f compose.deploy.yaml exec app python -m scripts.create_admin --role staff --activate
```

The interactive script prompts for the password without echo. `--activate` represents
an operator identity-verification decision, not an automatic identity check. Admin
accounts use `--role admin`. To seed the isolated registry with the bundled fictional
records, first validate and then explicitly apply using the separate importer identity:

```bash
docker compose -p unidays-stage7 --profile dev --profile tools -f compose.deploy.yaml run --rm registry-importer
docker compose -p unidays-stage7 --profile dev --profile tools -f compose.deploy.yaml run --rm registry-importer --apply
```

The importer receives only its own credential; the application does not receive it.
The example CSV is mounted read-only. Review the fictional records before applying.

## Checks and operating commands

```bash
docker compose -p unidays-stage7 --profile dev -f compose.deploy.yaml config --quiet
docker compose -p unidays-stage7 --profile dev -f compose.deploy.yaml ps
curl --cacert deploy/certs/localhost.crt -I https://localhost:5443/
docker compose -p unidays-stage7 --profile dev -f compose.deploy.yaml stop
```

Use `start` in place of `stop` to resume the existing containers, or `up -d` after a
configuration change. `stop` retains the separate database volume. Do not use
`down -v` unless intentionally deleting this deployment's data and verified backups.
MongoDB's init script runs only on an empty volume; changing environment passwords
later does not rotate existing database users. Rotate credentials deliberately through
MongoDB and update the corresponding secret files and clients together.

## Verification performed on 28 November 2026

- Compose configuration validated; all four services reported healthy after startup.
- `curl` verified the localhost certificate and received HTTP 200. A headless browser
  submitted a fictional failed sign-in over HTTPS and confirmed CSRF processing and a
  Secure session cookie. Full signup and email verification through nginx remain to be
  tested; an independent fictional SMTP message did reach the isolated Mailpit inbox.
- The app process reported UID 10001 and no `/app/.env` file. MongoDB had no published
  host port. The registry importer validated and inserted two fictional rows.
- The audit writer was denied reads; the audit reader and registry app were denied
  inserts. Statistics and registry reads succeeded. This is a focused check, not a
  comprehensive permission audit.
- The project regression suite reported **111 passed**, including the existing browser
  tests, against disposable databases; these tests do not all exercise this container.

## Pre-release checklist — all planned unless explicitly verified

- [ ] Replace local fake identity and Mailpit with approved institutional records and
      a real authenticated mail service or SSO; use a valid publicly trusted TLS cert.
- [ ] Enforce production secret validation and debug-off settings; protect and rotate
      secrets using a suitable secret manager. Pin and audit dependencies and images.
- [ ] Replace client-side sessions with revocable server-side sessions, and use a
      shared rate-limit store with proxy/IP trust explicitly tested.
- [ ] Provide reliable, monitored audit delivery and restricted, redacted log storage;
      establish retention and handling procedures for audit IP addresses.
- [ ] Use a transaction-capable MongoDB deployment where cross-document consistency
      is required; test database roles and restore from an independent backup.
- [ ] Implement and test key rotation and recovery; separate keys from ciphertext and
      account for plaintext remnants in snapshots and backups.
- [ ] Perform accessibility, mobile, incident response, privacy and legal reviews,
      including an institutional DPIA and appropriate Article 6/9 assessment.
- [ ] Perform a controlled security assessment and end-to-end production-style test;
      configure monitoring, availability and emergency support processes.

The configuration uses image tags rather than immutable digests and installs direct
Python dependencies without a hash lock. Docker environment variables and local
secret files can be read by sufficiently privileged host/container operators. Keep
the host, Docker access, backups and files protected; this design is not a production
secrets manager. See [hardening-review](hardening-review.md) and
[case-encryption](case-encryption.md) for remaining risks.
