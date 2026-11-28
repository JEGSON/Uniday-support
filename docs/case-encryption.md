# Case encryption for the local demo

Student descriptions, student replies, staff messages and private notes are encrypted before MongoDB storage. Each encrypted text contains a Fernet ciphertext and key ID; the authenticated payload binds it to the case reference and field type. The service decrypts only after its role and case-access checks. Missing, wrong or tampered keys/ciphertext fail closed, returning an unavailable response without logging the text or key.

`CASE_ACTIVE_KEY_ID` selects the key for new writes; `CASE_ENCRYPTION_KEYS` maps key IDs to Fernet keys. The local key is held in the ignored `.env`, which must never be committed or sent in chat. Make a separate secure offline backup of the key **before relying on the encrypted data**. If the key is lost, neither its cases nor backups encrypted with it can be recovered. Restrict access to `.env` and backups. A local file is not a production key-management service.

For a future key change, configure both the old and new keys under different IDs, switch the active ID, and restart all processes. Old keys must remain available to decrypt older entries and backups. The current migration encrypts plaintext only; it does **not** rotate existing encrypted entries. A tested rotation and retirement procedure is still required.

The migration defaults to a dry run:

```bash
.venv-secure/bin/python -m scripts.encrypt_cases
```

Before applying, stop **all** application processes and any other writers. A conditional update prevents a detected concurrent write from being overwritten, but the script cannot guarantee that another writer won't start afterwards. Once stopped:

```bash
.venv-secure/bin/python -m scripts.encrypt_cases --apply --offline-confirmed
```

Before any database updates the script creates an encrypted, permission-restricted backup under the Git-ignored `data/raw/case-backups/` directory, and compares each decrypted backup record to its source. The backup is encrypted with the active case key and contains pre-migration records; keep the key backup separately. The backup format is Fernet-encrypted BSON records in JSON Lines, not a `mongodump` archive. The project does not yet provide an operator-facing restore command. Backup verification at creation checks all original records, but the current archive format does not detect later removal of complete lines; retain a separately protected copy and record the expected case count. A failed or interrupted migration can leave a mixture of encrypted and plaintext records. The new application fails closed on plaintext; stop writers, keep the backup, investigate and rerun the migration rather than deleting records.

Not encrypted: category, status, timestamps, urgency, case reference, ownership and assignment IDs, version, audit metadata and the length of encrypted fields. Fernet tokens also expose their encryption timestamp. These fields support queries, queue ordering and access control but can reveal information. Encryption does not protect against a compromised running application, an attacker who obtains the key, logs created outside the application, or plaintext already present in older backups, MongoDB storage pages, journals or filesystem snapshots. This is not full-disk encryption or guaranteed secure erasure. Fernet authenticates each payload and prevents moving it across cases or field types in this design, but does not prevent replay/reordering of an encrypted item within the same case and field. Audit delivery is best effort, not atomic with case writes. Continue using fictional data only.

Reference: PyCA Cryptography. (n.d.). *Fernet (symmetric encryption)*. https://cryptography.io/en/latest/fernet/
