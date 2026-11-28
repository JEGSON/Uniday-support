# 07 — Evaluation, limitations and ethics

## What the evidence supports

The local prototype demonstrates role-aware case handling, owner and assignment
checks, private-note separation, authenticated encryption of case text, and a
registry/email-verification workflow. The Stage 4 run reported 105 passing automated
tests and 86.16% statement coverage on the measured application modules. Four focused
hardening tests passed later in a separate run. These are useful regression evidence,
not a production certification, complete security assessment, accessibility result or
proof of legal compliance. Detailed methods and gaps are in [06-test-plan](06-test-plan.md).

The project draws on ASVS as a verification framework and the OWASP Top 10 as an
awareness taxonomy; referencing them does **not** establish full ASVS compliance. The
15-character minimum for single-factor passwords, blocklist and lack of composition
rules are informed by NIST SP 800-63B-4; this project does **not** claim NIST
conformance or an authentication assurance level.

## Residual risks and trade-offs

- **Identity and delivery:** a local registry can become stale or be populated
  incorrectly. Mailpit accepts local mail and does not demonstrate ownership of a
  real institutional mailbox. A compromised inbox can expose a verification link.
  Neutral sign-up responses reduce enumeration but may confuse legitimate users.
  Institutional records and real mail or SSO are planned alternatives.
- **Sessions and abuse:** signed client-side cookies are not individually revocable
  after logout. In-memory IP limits reset and are not shared between workers; temporary
  account lockout can itself be abused to inconvenience a user. Revocable sessions,
  shared limits and suitable monitoring are planned.
- **Encryption and access:** key IDs allow multiple configured keys, but tested key
  rotation and backup restoration are planned. A lost key prevents recovery; a stolen
  key plus database or a compromised app can reveal content. Status, category, dates,
  ownership and audit metadata are visible, and older database pages or backups may
  retain plaintext. See [case-encryption](case-encryption.md).
- **Audit and integrity:** audit writes are best effort, not atomic with case changes,
  and logs are not hash-chained. An unexpected exception can reach logs with its text.
  Durable delivery, redaction and appropriate retention are planned. Hash chaining
  alone would not establish trustworthy logs without protection of its keys and anchors.
- **Concurrency:** conditional version updates reduce lost updates. A standalone
  database still has cross-document races, including account and assignment changes;
  a transaction-capable replica set is a possible future design.
- **Availability and service expectation:** the local prototype is not monitored and
  is not suitable for urgent requests. Denial-of-service, recovery and organisational
  support arrangements have not been established.
- **Usability and accessibility:** browser tests cover three journeys, but keyboard,
  screen-reader, 360px and contrast reviews are planned; no accessibility conformance
  is claimed. Privacy labels and neutral messages should be evaluated with users.

## Ethical and data-protection reflection

Student support details can disclose health or disability information, and even
metadata can identify a person in a small cohort. A reassuring visual design must not
imply that an unmonitored demo can provide urgent help. Only fictional data should be
used here; pseudonymisation alone does not necessarily remove data-protection duties.
Real deployment would need an institutional assessment of necessity, lawful basis,
special-category conditions, transparency, retention, accessibility, incident handling
and the risks of unequal access. A DPIA and specialist/institutional review are
planned, not completed. The ICO advises that special-category processing needs both an
Article 6 lawful basis and an Article 9 condition; the choice depends on the facts
(Information Commissioner's Office, n.d.-b).

The student should review these trade-offs, confirm project facts and adapt the report
to their own analysis rather than presenting generated draft text as independently
observed evidence. The [risk register](02-project-plan-risk.md) and
[hardening review](hardening-review.md) identify actions that remain open.

## References (APA 7 style)

Information Commissioner's Office. (n.d.-a). *Principle (c): Data minimisation*.
https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/a-guide-to-the-data-protection-principles/data-minimisation/

Information Commissioner's Office. (n.d.-b). *What are the rules on special category data?*
https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-are-the-rules-on-special-category-data/

Microsoft. (n.d.). *Threats — Microsoft Threat Modeling Tool*.
https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats

OWASP Foundation. (2025a). *Application Security Verification Standard 5.0.0*.
https://asvs.owasp.org/

OWASP Foundation. (2025b). *OWASP Top 10:2025*. https://top10.owasp.org/

Temoshok, D., Fenton, J. L., Choong, Y.-Y., Lefkovitz, N., Regenscheid, A., Galluzzo, R.,
& Richer, J. P. (2025). *Digital identity guidelines: Authentication and authenticator
management* (NIST SP 800-63B-4). National Institute of Standards and Technology.
https://doi.org/10.6028/NIST.SP.800-63B-4
