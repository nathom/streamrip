# Download database migration design

## Intent and goals

On application startup, upgrade existing SQLite tables to include columns required by the current application, without dropping tables or losing existing download history. Do not inspect or scan user folders to reconstruct values.

## Approaches

- **Add missing columns (selected):** inspect each known table and add columns absent from the current schema. This preserves current data and supports additive schema changes with minimal machinery.
- **Versioned migrations:** encode each historical schema transition explicitly. This is more suitable for complex transformations but adds bookkeeping and maintenance that this additive change does not need.

## Design and constraints

Implement the startup steps once in `DatabaseBase`, so every table subclass that supplies a `name` and `structure` gets the same behavior. On open, ensure the table exists with `CREATE TABLE IF NOT EXISTS`, inspect its columns, and add any missing columns with SQLite `ALTER TABLE`. Subclasses provide field-specific migration defaults for columns that need backfilling. In particular, legacy download rows can retain their IDs but cannot have their filepath inferred from the database alone; initialize that value neutrally rather than scanning the filesystem. Preserve existing rows and columns, and make migration errors visible rather than silently recreating a table.

New databases keep their current schema and behavior. No filesystem discovery, row deletion, or unrelated database format changes are in scope. More complex future schema changes may need explicit per-field migration rules.
