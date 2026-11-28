# 02 — Project plan and risk register

This is a current status and proposed plan, not a reconstructed historical schedule or
claim that milestones were achieved on particular dates. Owner and deadline are to be
agreed by the student and supervisor.

| Work package | Current status | Next acceptance activity |
| --- | --- | --- |
| Requirements, auth, registry and local email | Implemented for local demo | Review identity and email assumptions; institution integration is planned. |
| Case workflows and dashboard wiring | Implemented for local demo | Repeat student/staff end-to-end checks after changes. |
| Encryption and local migration | Implemented | Test restoration, rotation and independently protected key backup; planned. |
| Tests and security review | Automated evidence recorded | Keyboard, screen reader, mobile and contrast reviews are planned. |
| Documents | Drafted from current evidence | Student to check module rubric, add their own critical analysis and confirm facts. |
| Deployment and repository hygiene | Planned stages 7–8 | Implement and verify; no deployment or history-scan result is claimed here. |

Risk scores are qualitative estimates (likelihood × impact), not measurements.

| Risk | Likelihood / impact | Current treatment and residual risk |
| --- | --- | --- |
| R-01 Session cookie replay after logout | Medium / high | Signed cookies expire; individual revocation is planned. |
| R-02 Audit outage loses an event | Medium / high | Best-effort append and warning; durable atomic delivery is planned. |
| R-03 Key lost or exposed | Medium / high | Local key outside Git; tested restore, rotation and independent backup are planned. |
| R-04 Fake registry or mailbox compromise | Medium / high | Registry and Mailpit are local demonstrations; authoritative identity and real email/SSO are planned. |
| R-05 Sensitive information enters demo | Medium / high | UI warns users and fictional data is required; monitoring and institutional data governance are not implemented. |
| R-06 Concurrent update or assignment race | Medium / medium | Case versions and conditional claims help; cross-document transactions are planned. |
| R-07 Multi-worker rate-limit bypass or lockout abuse | Medium / medium | Local per-process IP limit and temporary account lockout; shared limits and monitoring are planned. |
| R-08 Disclosure via metadata, logs or snapshots | Medium / high | Data projection and encryption reduce exposure; metadata, older snapshots and unexpected exception logs need controls. |

The prioritised technical actions and reproducible checks are in
[hardening-review](hardening-review.md).
