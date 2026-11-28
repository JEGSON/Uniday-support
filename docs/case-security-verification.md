# Case management security verification

Run completed on 28 November 2026: **105 passed**, including three Playwright browser
journeys and integration tests using
disposable MongoDB databases and the local Mailpit service. The tests delete their
temporary databases after use. The results below describe the automated tests, not a
formal security assessment. Test cases and text are fictional.

| Test | Requirement | STRIDE category | Result |
| --- | --- | --- | --- |
| `test_student_form_persists_and_other_student_gets_404` | Students cannot open another student's case by changing its reference. | Information disclosure | Passed |
| `test_student_forgery_xss_denial_and_audit_events` | Forged owner, status and assignee fields cannot override server-side values; case text is escaped in HTML. | Tampering; elevation of privilege | Passed |
| `test_signup_verify_replay_and_signin` | A public registration with a forged admin role still creates a student. | Elevation of privilege | Passed |
| `test_operator_inputs_cannot_change_case_queries` | Dictionary-shaped MongoDB operators are rejected for case inputs and references. | Tampering; information disclosure | Passed |
| `test_submission_validation_and_csrf`; `test_staff_stale_updates_reassignment_and_audit` | Missing CSRF tokens reject student and staff changes. | Spoofing; tampering | Passed |
| `test_staff_stale_updates_reassignment_and_audit`; `test_legacy_versions_and_student_reply_invalidate_staff_form` | Stale versions cannot overwrite more recent staff or student changes. | Tampering | Passed |
| `test_concurrent_claims_and_assigned_access`; `test_staff_stale_updates_reassignment_and_audit` | Archived cases are hidden from student and staff detail services. | Information disclosure | Passed |
| `test_migration_and_new_writes_encrypt_raw_mongo` | Raw MongoDB documents do not contain the tested plaintext; authorised services can decrypt it. | Information disclosure | Passed |
| `test_mongosh_raw_case_has_no_plaintext` | Mongosh reads a disposable encrypted case without finding its description or note markers. | Information disclosure | Passed |
| `test_encryption_wrong_key_tampering_and_context`; `test_dashboards_fail_safely_with_wrong_encryption_key` | Wrong keys and altered or misplaced ciphertext fail closed; dashboard requests return 503. | Tampering; information disclosure | Passed |
| `test_unassigned_queue_exposes_metadata_but_not_case_detail`; `test_staff_workflow_http_and_private_notes` | Staff see an unassigned metadata queue, but cannot view its contents before claiming it or access another officer's case. | Information disclosure; elevation of privilege | Passed |
| `test_dashboard_context_never_receives_private_staff_notes` | Student template contexts do not receive the private staff note; the assigned staff view can receive it. | Information disclosure | Passed |
| `test_student_forgery_xss_denial_and_audit_events`; `test_all_staff_changes_write_content_free_audit_events` | Case creation, denied viewing, student replies and staff changes produce events without the tested case text. | Repudiation; information disclosure | Passed |
| `test_account_lockout_after_failed_passwords`; `test_signin_rate_limit` | Repeated failed sign-ins trigger account lockout and the IP rate limit. | Spoofing; denial of service | Passed |
| `test_deactivation_blocks_existing_session_on_next_request` | A deactivated user's existing session is refused on the next request. | Elevation of privilege | Passed |
| `test_browser_student_creates_and_views_request`; `test_browser_student_cannot_open_another_students_case`; `test_browser_staff_note_does_not_reach_student` | Browser journeys exercise persistence, owner isolation and private-note separation. | Tampering; information disclosure | Passed |

The mongosh test invokes the shell automatically against a throwaway database; it is not
a manual inspection of the live database. The checks prove that tested documents do not
contain the markers, not that every storage artifact is plaintext-free.

To repeat the suite, activate the project environment, set `TEST_MONGODB_URI` to a
local MongoDB identity allowed to create and drop disposable databases, then run:

```bash
TEST_MAILPIT=1 RUN_BROWSER_TESTS=1 RUN_MONGOSH_TESTS=1 python -m pytest -q --cov=app --cov=db --cov=services --cov-fail-under=70
```

Install the free development tools with `python -m pip install -r requirements-dev.txt`.
Install a Playwright Chromium browser with `python -m playwright install chromium`, or
set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` to an existing compatible local browser. Docker
Compose MongoDB and Mailpit must be running. Use a test-only MongoDB identity and do not
paste its connection string into reports or chat. The mongosh test uses the local
container's configured root identity solely to inspect its disposable test database;
this is not a production least-privilege example. Without the flags or test database,
checks are skipped; a green result with skips is not equivalent to the run above.

The coverage target is **70% statement coverage** for `app`, `db` and `services`.
The run achieved **86.16%**. This does not cover every branch, script or UI state and
is not a measure of security completeness.

## Automated security tools

Bandit 1.9.4 scanned `app.py`, `db.py`, `services` and `scripts`: **10 findings**
(nine low, one medium). No finding was suppressed. Review of every occurrence:

| Finding | Location | Review and remaining risk |
| --- | --- | --- |
| B105 low | `app.py:129`, `app.py:139` | Empty verification-token placeholders, not credentials. No action needed. |
| B311 low | `scripts/seed_cases.py:81` | Seeded pseudorandom generator produces fictional fixture content; opaque references use `secrets`. Do not use it for secrets. |
| B105 low | `services/audit_viewer.py:11` | Human-readable expired-link event text, not a token. |
| B105 low | `services/enrollment.py:34`, `services/enrollment.py:36` | Initial `password_hash` is `None` until the mailbox owner completes verification; not a hardcoded password. |
| B608 medium | `services/mail.py:23` | Plain-text email body assembled using a validated local base URL and token; no SQL query exists in this function. Header values are set separately. |
| B105 low | `services/registry.py:15` (two occurrences) | Constant validation-only placeholder and confirmation, never assigned as a user credential. |
| B105 low | `services/users.py:53` | Password mismatch error message, not a password. |

`pip-audit 2.10.1 -r requirements.txt` reported **no known vulnerabilities** on this
run. It covers pinned application requirements and their resolved dependencies, not
every package in the development environment or unknown vulnerabilities. Repeat both
checks before release; their results change as code and advisories change.

## Residual risks and scope

The unassigned queue is an intentional access choice: it reveals limited case metadata
to staff so they can claim work; case details require assignment. The tests do not prove
that the UI is accessible, the deployment is hardened, or production permissions are
correct. Audit writes are best effort and are not atomic with case changes, so an audit
outage can leave a missing event. Status, category, timestamps and assignment remain
unencrypted, and a compromised running application or stolen key can expose content.
See [case encryption](case-encryption.md) for backup, migration and key limitations.
