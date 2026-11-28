# 05 — Traceability matrix

Each row traces a scenario through one business need, security requirement, STRIDE
threat, mitigation and test. Definitions appear in [01-requirements](01-requirements.md),
[03-threat-model](03-threat-model.md) and [06-test-plan](06-test-plan.md). The matrix
does not claim that a passing test eliminates the threat.

| Scenario | Need | Requirement | Threat | Mitigation | Test | Current result |
| --- | --- | --- | --- | --- | --- | --- |
| Student signs in / attacker guesses | BR-01 | SR-01 | T-01 | M-01 | TC-01 | Passed; session revocation planned |
| Student registers with registry details | BR-02 | SR-02 | T-02 | M-02 | TC-02 | Passed locally; real identity proof planned |
| Student opens a case | BR-03 | SR-03 | T-03 | M-03 | TC-03 | Passed |
| Officer opens or claims a request | BR-04 | SR-04 | T-04 | M-04 | TC-04 | Passed |
| Officer or student updates a case | BR-05 | SR-05 | T-05 | M-05 | TC-05 | Passed |
| Database reader inspects case text | BR-06 | SR-06 | T-06 | M-06 | TC-06 | Passed for tested fields; metadata visible |
| Visitor forges role or query values | BR-07 | SR-07 | T-07 | M-07 | TC-07 | Passed |
| Investigator reviews a change | BR-08 | SR-08 | T-08 | M-08 | TC-08 | Passed when audit is available; durable delivery planned |
| Attacker floods sign-in | BR-09 | SR-09 | T-09 | M-09 | TC-09 | Passed in one local process; shared limiting planned |

Coverage scope: all BR/SR/T/M/TC IDs defined in these numbered project documents occur in
this matrix. The separate risk register and Stage 5 hardening list contain additional
risks and planned work; they are not claimed to be completely captured by nine rows.
