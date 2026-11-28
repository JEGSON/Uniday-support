# 06 — Test plan and recorded results

## Environment and scope

The last complete Stage 4 run on 28 November 2026 used Python 3.12, Flask test
client, temporary local MongoDB databases, local Mailpit and headless Chrome via
Playwright. It reported **105 passed**, **86.16% statement coverage** for `app`, `db`
and `services`, against a **70% target**. Four subsequent focused hardening tests
passed separately; a combined run including those four is not claimed here. Results
are historical and should be rerun after code changes. Test databases are disposable;
test data is fictional. Coverage does not measure security effectiveness or include all
scripts, branches, browser combinations or manual accessibility checks.

## Traceable tests

| Test | Requirement | STRIDE | Result and concrete evidence |
| --- | --- | --- | --- |
| TC-01 | SR-01 | Spoofing | Passed: `test_account_lockout_after_failed_passwords` and `test_signin_rate_limit`; cookie replay after logout remains planned. |
| TC-02 | SR-02 | Spoofing | Passed: `test_signup_verify_replay_and_signin`, `test_wrong_registry_details_and_simultaneous_claim`, and local Mailpit journey. |
| TC-03 | SR-03 | Information disclosure | Passed: `test_student_form_persists_and_other_student_gets_404` and browser IDOR journey. |
| TC-04 | SR-04 | Elevation of privilege, information disclosure | Passed: assigned-access, unassigned-queue and student-context tests, plus browser note separation. |
| TC-05 | SR-05 | Tampering | Passed: stale update and missing-CSRF checks. |
| TC-06 | SR-06 | Information disclosure, tampering | Passed: encryption, wrong-key/tamper tests and automated mongosh inspection of test markers. |
| TC-07 | SR-07 | Elevation of privilege, tampering | Passed: forged admin signup role, forged case fields, operator input rejection and escaped XSS marker. |
| TC-08 | SR-08 | Repudiation | Passed with audit available: student and staff event tests. Durable delivery during audit failure: planned, not passed. |
| TC-09 | SR-09 | Denial of service | Passed in local single-process tests: rate limit, temporary lockout, input bounds and unavailable-service response. Distributed/availability tests planned. |

Three browser tests exercise student creation, cross-student denial, and staff note
privacy. The mongosh check uses a fictional record in a throwaway database. A
deactivated existing session is refused in `test_deactivation_blocks_existing_session_on_next_request`.
Bandit and pip-audit findings and repeat instructions are in
[case-security-verification](case-security-verification.md); the Stage 5 controls and
their focused tests are in [hardening-review](hardening-review.md).

## Manual checks — planned, no results claimed

| Check | Procedure | Result |
| --- | --- | --- |
| Keyboard | Navigate student, staff and admin flows; confirm focus, dialog trapping and Escape. | Planned |
| Screen reader | Review labels, landmarks, status updates and dialogs using VoiceOver or NVDA. | Planned |
| Mobile | Inspect all dashboards and dialogs at 360px. | Planned |
| Contrast | Run an accessible contrast checker and inspect focus/error states. | Planned |
| Production TLS, backup restore and key rotation | Exercise a staged deployment and disposable recovery. | Planned |

How to repeat the complete Stage 4 run and required environment flags is described in
[case-security-verification](case-security-verification.md). Do not paste credentials,
keys or real case contents into reports.
