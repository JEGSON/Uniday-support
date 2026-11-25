# Local password blocklist

`ncsc_100k_passwords.txt` is the NCSC 100k common-password list distributed by
[SecLists](https://github.com/danielmiessler/SecLists/blob/master/Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt).
The SecLists MIT license is reproduced in `SECLISTS_LICENSE.txt`. Downloaded
2026-11-25; SHA-256: `c2e5696882c603b76bb67a47ee970897e5a76fc4c3f5547abe3d0ca340c576e0`.
`common_passwords.txt` adds local examples and application-specific passwords.

These static lists are incomplete and age over time; they cannot establish that
a password has never appeared in a breach. Review and update the source regularly.
Compare the whole normalized password, not substrings. Do not submit passwords
to an online service in this local-only design.
