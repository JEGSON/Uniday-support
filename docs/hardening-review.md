# Stage 5: security hardening review

Review date: 28 November 2026. Scope: the local application code and configuration
templates, not an independent penetration test, Git history scan, live MongoDB
privilege audit or production deployment. Proposed fixes below are **planned** unless
explicitly described as existing. Continue using fictional records in the local demo.

## Prioritised fixes

| Priority | Finding and threat | Existing control / planned fix | How to verify |
| --- | --- | --- | --- |
| High | A stolen signed session cookie can be replayed after logout until expiry. A copied cookie can continue to impersonate a user. | Existing logout clears the browser session and roles are reloaded from MongoDB; this does not revoke a copied cookie. **Planned:** use server-side session identifiers with revocation, expiry and a shared session store. | In an isolated test, save a cookie before logout, log out, then replay the saved cookie. The planned fix must refuse the replay. |
| High | In production, `SECRET_KEY` must be 32 characters, but length does not establish entropy and the long example placeholder passes the check. A predictable signing key enables session forgery. `APP_ENV` is read from the process environment, not the local dotenv settings. | Existing code rejects absent or short keys in production. **Planned:** reject known placeholders and provisioning mistakes, generate a random secret outside Git, explicitly set and verify `APP_ENV=production` in deployment. Length checks cannot prove randomness. | `tests/test_hardening_review.py` checks absent and short production secrets. Add a placeholder-rejection test when implemented; inspect configuration without printing its value. |
| High | Debug mode is not explicitly refused when `APP_ENV=production`; deployment or the Flask CLI can enable it. An exposed interactive debugger can compromise the host. | **Planned:** fail startup if production debug is enabled, and configure the production server with debug off. | Add tests for conflicting production/debug settings and verify the actual deployed process and error responses with a harmless test error. |
| High | Audit writes are best effort and occur after changes. An outage can silently leave a case or privileged change without an audit event. | Existing code logs a generic warning. **Planned:** durable, atomic audit design, e.g. a transactional outbox and protected delivery/retry on an appropriately configured replica set; separately secure and monitor delivery. | Simulate audit-store failure before and after a change; verify the chosen design never loses an acknowledged event and alerts on failed delivery. |
| High | Fernet keys and backups are local files; losing the key loses access and disclosure of both key and database exposes case text. Restore and re-encryption procedures are not implemented. | Existing encryption and key IDs, with documented limitations. **Planned:** tested restore, rotation and retirement procedures and independently protected key backup. | Perform recovery and rotation against an isolated disposable database and verify old/new records, backup integrity and retained keys. |
| Medium | Unhandled exception messages can contain sensitive information and Flask logs them. A generic browser error does not guarantee safe server logs. | Explicit application warnings do not interpolate passwords or tokens. The hardening test demonstrates a fictional exception marker appears in captured logs. **Planned:** minimise exception content and implement reviewed, tested redaction and restricted retention for application, proxy and server logs. | `python -m pytest -q tests/test_hardening_review.py`; inject fictional markers into failure paths, inspect controlled logs without exposing real secrets. |
| Medium | In-memory rate limits are per process and reset on restart; multiple workers can bypass an intended global limit. | Existing per-IP limits and per-account temporary lockout. **Planned:** a shared limiter store with protected access and correctly configured trusted proxy IP handling. | Test failed logins across multiple workers and restart; verify account and IP limits and spoofed forwarding headers. |
| Medium | Last-admin and staff-reassignment safeguards span multiple documents without transactions. Concurrent changes may violate the intended invariant. | Existing conditional updates reduce some races. **Planned:** use a replica set and transaction or another design that enforces the invariants atomically. | Run simultaneous conflicting operations in an isolated replica-set test and inspect the final state. |
| Medium | Application requirements are version-pinned, but transitive dependencies are not locked and updates may introduce vulnerabilities. | Existing `requirements.txt` pins direct dependencies; Stage 4 pip-audit found no known issues on its run. **Planned:** use a reviewed, hash-locked dependency set and routinely repeat auditing. | Rebuild in a clean environment from the lock, verify hashes and run `python -m pip_audit -r requirements.txt`. |
| Medium | The example environment has placeholders, but the actual database users, their permissions and deployed credentials were not inspected in this review. | Existing example requires replacement values; compose keeps MongoDB and Mailpit on localhost for the local demo. **Planned:** independently check no default/shared credentials and prove least privilege for each database identity; scan Git history and rotate any exposed secret. | Use a disposable negative-permission test for each role; inspect credential configuration without printing values. Complete the history scan in Stage 8. |
| Low | `services.users.create_student` appears unused by the current registration route and represents an additional write path to maintain. | Current signup uses registry-backed enrollment. **Planned:** trace external/script references and either remove the unused helper or document and test its purpose; do not delete it solely on a superficial search. | Search repository references and run the suite after any removal. |
| Low | User-facing 404 and 500 responses use Flask defaults rather than tailored pages; unhandled exceptions need further log controls. | With debug off, the test receives generic responses without the fictional exception message. **Planned:** review generic error UX and deployment error handling without revealing internals. | Test unknown routes and a deliberately raised fictional exception with debug disabled; inspect the response and secure logs separately. |

## Existing controls verified in this stage

`tests/test_hardening_review.py` produced **4 passed** in its focused run:

- Production rejects missing or short session secrets. It does not prove secret entropy.
- A production-mode sign-in response sets `Secure`, `HttpOnly` and `SameSite=Lax`
  session cookie flags; CSP includes self-hosted scripts and `frame-ancestors 'none'`,
  with `nosniff`, HSTS and `no-store` on sign-in. Test in a real TLS deployment too.
- A sign-in URL containing an external `next` parameter redirects to the internal
  role dashboard. The app currently ignores `next`; any future use must validate it.
- Every currently registered POST rule returns 400 when sent without a CSRF token.
  This checks server enforcement, not whether every valid form works in every browser.
- With debug off, a controlled exception is absent from the 500 response but appears
  in captured server logs; this is a demonstrated residual risk, not a passed
  log-redaction control.

To repeat these focused checks, activate the project environment and run:

```bash
python -m pytest -q tests/test_hardening_review.py
```

For a browser review, use developer tools to inspect response headers and test the
existing pages for CSP violations. HSTS is only sent when `APP_ENV=production`; do not
enable it against a real domain until HTTPS and subdomain implications are understood.
The CSP has not been exhaustively tested against every browser or dynamic page here.
