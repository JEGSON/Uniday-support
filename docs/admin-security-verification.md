# Admin dashboard security verification

Local development only; never enter real sensitive information. The audit log is best effort and is not hash chained. Staff and admin accounts are created using the secure CLI. Web changes protect all existing admin accounts, not just the last one, to avoid a standalone-MongoDB last-admin race; changing an existing admin requires a controlled database-operator procedure, which is not yet provided by the CLI. Re-activation requires verification flags; older CLI-created staff accounts without `identity_verified` cannot be reactivated in the web interface. User listing currently stops at 100 entries. Changes to active status and role are read from MongoDB on the next request; previously issued signed session cookies are not independently revocable and a request already in flight is not recalled.

## Database privileges

The configured `stats_reader` has only `find` on `cases_db.cases`. MongoDB's `find` privilege also permits retrieval of complete documents: returning counts only is an application boundary, not database-enforced field protection. The Flask process also holds the normal cases and auth credentials. A stronger design uses an independently maintained aggregate collection and separate service. Small buckets are suppressed together to limit subtraction attacks, but totals and repeated queries can still disclose small cohorts.

The configured `audit_app` has only `insert` and `createIndex` on `audit_db.events`; `audit_reader` has `find` only. The existing `unidays_app` retains its earlier insert-only `auditEventWriter` role even though the new code uses `audit_app`; remove that legacy grant after restarting the application and checking audit delivery. Neither identity's permissions are a defence against an administrator with root MongoDB credentials. Audit records contain IP addresses, which are personal data; consider truncation and a retention policy after assessing investigation needs. Events deliberately omit passwords, raw verification tokens and case text, but historical events require separate review before claiming they never contained sensitive data.

For a fresh local installation, connect to the local MongoDB container as an operator with user/role administration privileges using `mongosh`, then select the relevant database and run the following. Replace password placeholders interactively with `passwordPrompt()`; keep URI credentials in the ignored `.env` only. Back up and inspect any existing roles first; do not replace an existing role blindly.

```javascript
use cases_db
db.createRole({role: 'case_stats_read', privileges: [{resource: {db: 'cases_db', collection: 'cases'}, actions: ['find']}], roles: []})
db.createUser({user: 'stats_reader', pwd: passwordPrompt(), roles: [{role: 'case_stats_read', db: 'cases_db'}]})
use audit_db
db.createRole({role: 'audit_append_only', privileges: [{resource: {db: 'audit_db', collection: 'events'}, actions: ['insert', 'createIndex']}], roles: []})
db.createRole({role: 'audit_find_only', privileges: [{resource: {db: 'audit_db', collection: 'events'}, actions: ['find']}], roles: []})
db.createUser({user: 'audit_app', pwd: passwordPrompt(), roles: [{role: 'audit_append_only', db: 'audit_db'}]})
db.createUser({user: 'audit_reader', pwd: passwordPrompt(), roles: [{role: 'audit_find_only', db: 'audit_db'}]})
db.events.createIndex({timestamp: -1, _id: -1}, {name: 'audit_timeline'})
```

To verify privileges manually, connect separately as `audit_app` and `audit_reader` (using password prompts, not passwords in shell history). In the writer session, `db.events.findOne()` should return unauthorized; in the reader session `db.events.insertOne({event_type: 'permission_test'})` and `db.events.deleteOne({event_type: 'permission_test'})` should both return unauthorized. Never run permission tests against production data.

## Automated tests and STRIDE

Results below describe the last local integration run with isolated throwaway MongoDB databases; rerun after changes.

| Test | Requirement | STRIDE category | Result |
| --- | --- | --- | --- |
| Admin route access and missing CSRF | Restrict role and prevent forged form submissions | Elevation of privilege, Tampering | Passed |
| Overview markers absent | Do not display case descriptions or notes | Information disclosure | Passed |
| Own and other admin changes denied | Preserve active admin accounts | Tampering, Denial of service | Passed |
| Invalid role and operator types | Validate inputs before MongoDB | Tampering, Elevation of privilege | Passed |
| Deactivated session on next request | Enforce current account status | Spoofing, Elevation of privilege | Passed |
| Unknown audit filters ignored | Validate filters | Tampering | Passed |
| Audit events for activation, deactivation and role change | Record privileged operations | Repudiation | Passed |
| Audit writer read and reader write/delete denied | Separate audit privileges | Tampering, Information disclosure | Passed locally; manual MongoDB permission checks |
| Category suppression | Reduce small-count disclosure | Information disclosure | Passed |
| Simultaneous admin changes | Preserve last active admin | Denial of service | All admin targets blocked in web UI; external changes are outside this guarantee |

## Manual accessibility and visual review

| Check | Procedure | Result |
| --- | --- | --- |
| Keyboard | Tab through all dashboard links and form controls; open dialogs, check focus, Esc and return focus | Not yet tested |
| Screen reader | With VoiceOver or NVDA, navigate landmarks, tables, labels, status notices and dialogs | Not yet tested |
| Mobile | Inspect all dashboard pages at 360px and larger, including the user table and filters | Not yet tested |
| Contrast | Run Lighthouse or axe DevTools and manually inspect states and focus | Not yet tested |

## References

- OWASP Foundation. (n.d.). *Authorization cheat sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP Foundation. (n.d.). *Logging cheat sheet*. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Foundation. (n.d.). *Application Security Verification Standard*. https://owasp.org/www-project-application-security-verification-standard/
- MongoDB. (n.d.). *Privilege actions*. https://www.mongodb.com/docs/manual/reference/privilege-actions/
- Kent, K., & Souppaya, M. (2006). *Guide to computer security log management* (NIST SP 800-92). https://doi.org/10.6028/NIST.SP.800-92
- Information Commissioner's Office. (2012). *Anonymisation: Managing data protection risk*. https://ico.org.uk/media/1042731/anonymisation_code_summary.pdf
