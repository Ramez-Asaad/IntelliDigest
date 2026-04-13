# Auth edge-case plan

## Goals

- Cover sign-up / sign-in edge cases with automated tests.
- Return clear HTTP errors where the UI can guide users (Google-only vs password, weak password).

## Edge cases → tasks

| Task | Edge case | Expected behavior |
|------|-----------|-------------------|
| A | Register with invalid email / short password | 400 with clear `detail` |
| B | Register duplicate email (password account) | 400 "Email already registered" |
| C | Register when email exists as **Google-only** | 400 "linked to Google… Use Continue with Google" |
| D | Password equals email (or trivial) | 400 rejection at registration |
| E | Email login: **Google-only** account (no password login) | 401 with message to use Google |
| F | Email login: wrong password (normal account) | 401 generic invalid credentials |
| G | Email login: unknown email | 401 generic (avoid enumeration where reasonable) |
| H | User had email+password, then signs in with Google (same email) | Link `google_sub`; password login still works |
| I | **Forgot password** | Not implemented: explicit 501 + message (or future reset flow) |

## Implementation notes

- **Schema**: `password_login_allowed` (0 = OAuth-only for new Google signups; 1 = may use password). Linked accounts stay 1.
- **Tests**: isolated SQLite DB via `tmp_path`, `JWT_SECRET` set for token assertions.
- **Password rules**: equality to full email or to local-part (before `@`) is rejected before the length check so errors stay specific.
- **Forgot password**: `POST /api/auth/forgot-password` returns **501** until a reset flow exists.

## Run tests

```bash
python -m pytest tests/test_auth_edge_cases.py -q
```
