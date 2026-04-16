# AGPL-3.0 Compliance & Security Audit

**Date:** 2026-04-15
**Repo:** Manna (backend fork of Mealie)
**Auditor:** Claude — Security & Architecture Design Assistant
**Purpose:** Pre-public-commit readiness check

---

## 1. License Compliance

### LICENSE file
**Status: PASS** — Root `LICENSE` file present with correct AGPL-3.0-or-later identifier, Mealie fork attribution, and copyright notice.

### SPDX Headers on Source Files

| Category | Files Checked | Headers Present | Missing |
|---|---|---|---|
| Python (.py) | 17 | 17 | 0 |
| SQL migrations | 1 | 1 | 0 |
| Dockerfile | 1 | 1 (remediated) | 0 |

**Remediation applied:** Added `SPDX-License-Identifier: AGPL-3.0-or-later` header to `backend/Dockerfile`.

---

## 2. Secrets & Credentials Scan

### backend/.env (real credentials)
**Status: SAFE** — File contains production-grade `POSTGRES_PASSWORD` and `JWT_SECRET` but is correctly excluded by `.gitignore`. Will NOT enter the public repo on first commit.

**Action required before deployment:** Rotate these secrets. They have existed on-disk and could appear in backups, shell history, or editor undo files. Generate fresh credentials for production.

### Hardcoded Defaults in config.py
**Status: ACCEPTABLE (annotated)** — `config.py` contains development-only defaults (`manna_dev`, `CHANGE-ME-in-production`). These are overridden by `.env` via `pydantic_settings` and are standard practice for local-dev ergonomics. Comments added to clarify intent.

### .env.example
**Status: PASS** — Contains only placeholder values (`replace-with-strong-random-password`). Safe for public commit.

### docker-compose.yml
**Status: PASS** — References `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}` via variable interpolation. No hardcoded secrets.

---

## 3. .gitignore Coverage

| Pattern | Purpose | Status |
|---|---|---|
| `.env`, `backend/.env` | Secrets files | Present |
| `__pycache__/`, `*.py[cod]` | Compiled bytecode | Present |
| `.venv/`, `venv/`, `env/` | Virtual environments | Present |
| `pgdata/` | Postgres data volume | Present |
| `.claude/` | Local Claude config | **Added** (remediation) |

**Remediation applied:** Added `.claude/` to `.gitignore` to prevent `.claude/settings.local.json` from being tracked.

---

## 4. __pycache__ / Bytecode

21 `.pyc` files exist in the working directory under `__pycache__/` directories. These are properly excluded by `.gitignore` and will not enter the repo. No action needed — they'll be ignored on `git add`.

---

## 5. Summary

| Finding | Severity | Resolved |
|---|---|---|
| Dockerfile missing AGPL header | Medium | Yes — header added |
| `.claude/` not in `.gitignore` | Medium | Yes — pattern added |
| Real secrets in `backend/.env` | Info | Already gitignored; rotate before deploy |
| Dev defaults in `config.py` | Low | Annotated with comments |

**Verdict: READY FOR INITIAL PUBLIC COMMIT** — after applying the remediations above (already done), the repo is clean for `git init && git add . && git commit`.

---

## Recommended Next Steps

1. **Initialize git repo** and make initial commit
2. **Rotate secrets** in `backend/.env` before any production deployment
3. **Add a pre-commit hook** (e.g., `detect-secrets` or `gitleaks`) to prevent future secret leaks
4. **Consider adding** a `CONTRIBUTING.md` noting AGPL-3.0 header requirements for new files
