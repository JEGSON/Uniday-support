# 01 — Requirements

**Scope and status.** Unidays Support is a local, fictional-data demonstration for
COM7033. It is not a monitored support service or a deployment for real personal
information. The identifiers below are project identifiers, not OWASP ASVS IDs.
Acceptance evidence and limitations are in [06-test-plan](06-test-plan.md).

| Business need | Scenario / acceptance need | Security requirement |
| --- | --- | --- |
| BR-01 | A registered student signs in to the correct dashboard. | SR-01: Validate credentials using a slow password hash, limit attempts and avoid account enumeration. |
| BR-02 | A student owns an account linked to their registry record. | SR-02: Match a validated unclaimed registry ID/email and require a one-time email confirmation before activation. Mailpit demonstrates the flow only. |
| BR-03 | A student makes and revisits their own request. | SR-03: Scope every case read and reply to the authenticated owner; return 404 for inaccessible cases. |
| BR-04 | A support officer manages only work assigned to them. | SR-04: Enforce role and assignment on case detail/actions; permit an unassigned metadata queue for claiming. |
| BR-05 | Case updates remain accurate if two people work concurrently. | SR-05: Validate allowed transitions, reject stale versions and use CSRF-protected POSTs for state changes. |
| BR-06 | Private case content is not exposed to unrelated users or database readers. | SR-06: Encrypt case text before storage and exclude staff notes from student context and descriptions/notes from admin overview. |
| BR-07 | A user cannot make themselves staff or admin. | SR-07: Derive actor/role from the server, validate user input as scalars and restrict privileged accounts to the CLI. |
| BR-08 | Security-relevant changes can be investigated. | SR-08: Record bounded audit events without passwords, tokens or case text; stronger guaranteed delivery is planned. |
| BR-09 | Staff can keep using the service during expected abuse or failures. | SR-09: Bound inputs and rate-limit sign-in; return safe errors and protect resources. Distributed limiting and availability guarantees are planned. |

For full scenario → threat → mitigation → test relationships see
[05-traceability-matrix](05-traceability-matrix.md). The UI's label “Received”
corresponds to the `New` status for newly created cases; legacy `Received` records
remain supported. No requirement here establishes emergency-service availability.

## Privacy requirements and assumptions

Development data is fictional. If real use is proposed, the institution must determine
controller responsibilities, purpose, retention, access rights and notices, an Article 6
lawful basis, and, where information reveals health or another special category, an
Article 9 condition. Disability or wellbeing descriptions may contain health data;
classification depends on content, not just the label. A DPIA and institutional review
are planned before any real processing, not claimed complete. Minimise records, avoid
case details in audit events and restrict access to operational metadata and IP addresses.
[ICO special-category guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-rules-on-special-category-data/)
explains the separate Article 6 and Article 9 requirements; its
[data-minimisation guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/)
notes that guidance is under review. These documents do not establish legal compliance.
