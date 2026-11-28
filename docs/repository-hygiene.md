# Repository hygiene review

Review date: 28 November 2026. Results apply to the local repository and checked-out
working tree at scan time. No remote fetch or push was performed for this review, so
remote references reflect the most recently fetched state.

## Secret scanning

Gitleaks `v8.28.0` ran locally in a container without network access to scan available
Git refs using `git --log-opts=--all`, with secret values redacted. It reported **64
commits scanned and one candidate**: a generic API-key pattern in
`tests/test_hardening_review.py`, line 13, in local snapshot commit `8b85ec3`.
Review established that the literal was an explicitly fictional test-only marker; its
line literals did not equal the values read from the local configuration files. It was
not on a named local or cached remote branch at review time. The fixed test value has
been replaced in the working tree with a random per-run test key. The old fictional
marker remains in that snapshot; it is not a deployed credential and was not rotated.
No actual secret was identified by this scan. This does not prove that no secret exists:
rules have coverage limits, and unreachable objects, un-fetched remote refs and systems
outside this repository were not exhaustively assessed.

A separate Gitleaks directory scan of 117 non-ignored tracked and untracked working-tree
files initially found the same fictional marker; a rescan after the change found **zero
candidates**. Ignored environment files, local datasets, virtual environments and
backups were deliberately excluded. The four focused hardening tests passed after the
change. Redacted reports and a temporary copy of the scanned files are under ignored
`data/raw/security-scan/`; keep them local and do not commit them.

If a future finding is a real credential, revoke or rotate it at the issuing service
first, investigate its use and exposure, and follow an appropriate incident response
process. Deleting a file or rewriting history alone does not revoke a credential.

## Data and credentials

- `.env`, `.env.*` except `.env.example`, deployment certificates and private keys,
  local virtual environments, raw/processed data, other CSVs under `data/`, and common
  SQLite/database files are ignored. The rules were checked with `git check-ignore`.
- The only tracked CSV is the small fictional registry example; it is explicitly
  exempted so the deployment importer can demonstrate its workflow. The available Git
  history filename review found that example and no other CSV or ZIP path.
- MongoDB data for this project is kept in Docker volumes, outside the repository; no
  claim is made about every file that could be created elsewhere on the machine.
- `.env.example` lists names and placeholders, not working passwords. A placeholder can
  still pass the current production secret-length check; fixing that remains planned
  in [hardening-review](hardening-review.md).
- UCI source, attribution, CC BY 4.0 licence and modifications are documented in
  [dataset-licence](dataset-licence.md).

## Branches and commits

At review, `main` had **16 commits**; its history includes at least eight descriptive
implementation commits and earlier pull-request merge commits. Some older messages
are generic, and local agent-session snapshots use automated messages. `main`, `develop`
and several `feature/*` branches exist. The local `develop` branch was shown as one
commit behind its cached `origin/develop`; no fetch or synchronization was performed.

Stages 3–8 remain uncommitted on `feature/field-encryption`. The current work has not
been pushed or merged by a pull request. A descriptive commit and pull-request review
are **planned** when the user requests them; do not claim a completed PR for this work.
