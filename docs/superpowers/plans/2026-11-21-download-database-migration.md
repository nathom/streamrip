# Download Database Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared startup schema check that creates missing tables and adds missing columns without losing existing database rows.

**Architecture:** Put table creation and additive column reconciliation in `DatabaseBase`, using each subclass's `name` and `structure`. Define safe defaults for legacy rows where needed; legacy download filepaths use an empty string because reconstructing them would require filesystem access.

**Tech Stack:** Python, SQLite (`sqlite3`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-download-database-migration-design.md`

## Global Constraints

- Preserve existing rows and columns.
- Do not scan user folders or infer filepaths from filesystem contents.
- Use a neutral value for legacy filepaths that cannot be derived from the database.
- Make migration failures visible rather than silently recreating a table.

## Review Focus

- Existing `downloads` rows with no `filepath` retain their IDs and get an empty filepath — test the old `id`-only schema.
- Reopening a migrated database does not duplicate columns or change existing values — test repeated initialization.
- A table absent from an existing database file is created — test `CREATE TABLE IF NOT EXISTS` behavior.
- The shared migration applies to a table other than `Downloads` — test another `DatabaseBase` subclass with a missing column.
- Existing row data is not changed by migration — assert row values before/after for each migration case.

---

### Task 1: Add generic schema reconciliation to database wrappers

**Files:**
- Modify: `streamrip/db.py`
- Test: `tests/test_db_replacements.py`

**Interfaces:**
- Consumes: Each `DatabaseBase` subclass's `name`, `structure`, and optional `migration_defaults: dict[str, str]` class attribute.
- Produces: `DatabaseBase` initialization that ensures the declared table exists and adds missing columns; `Downloads.migration_defaults["filepath"] == ""`.

- [x] **Step 1: Add failing migration tests**

Add tests that:
  - create a legacy `downloads` table containing `id TEXT UNIQUE NOT NULL` and a row, initialize `Downloads`, and assert `all()` returns the original ID with an empty filepath;
  - initialize `Downloads` twice and assert the row and schema remain unchanged;
  - open a database file that exists but does not contain the target table and assert the wrapper creates it;
  - create a legacy table for another `DatabaseBase` subclass with one declared non-unique column absent and `migration_defaults` set for that column, initialize the wrapper, and assert the old row is preserved and the missing column is populated with its configured default.

- [x] **Step 2: Run the targeted tests and confirm they fail**

Run: `pytest tests/test_db_replacements.py -q`
Expected: New migration tests fail because existing tables are not reconciled by `DatabaseBase`.

- [x] **Step 3: Implement shared reconciliation in `streamrip/db.py`**

Update `DatabaseBase` initialization to ensure the table exists using `CREATE TABLE IF NOT EXISTS`, inspect current columns with SQLite metadata, and add only missing columns. Preserve current create-time constraints. Use the subclass's `migration_defaults: dict[str, str]` for fields that must be backfilled; configure `Downloads.migration_defaults["filepath"]` as `''`. If a missing field has no safe migration default, fail visibly instead of adding invalid data. Remove the `Replacements`-specific table creation override so it uses the common path. Do not catch and suppress SQLite migration errors.
Select declared columns in `structure` order when returning rows, since SQLite appends migrated columns and the existing callers rely on stable tuple order.

- [x] **Step 4: Run targeted and full tests**

Run: `pytest tests/test_db_replacements.py tests/test_track.py -q`
Expected: PASS.

- [x] **Step 5: Commit the implementation**

```bash
git add streamrip/db.py tests/test_db_replacements.py
git commit -m "feat: migrate database columns on startup"
```
