# Config Version Suffix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mark fork configs as `2.2.0-sla` and automatically migrate upstream `2.2.0` configs without losing shared user settings.

**Architecture:** Reuse the exact config-version comparison and existing config updater. Keep the application/package version unchanged; the bundled config template supplies defaults for fork-specific keys.

**Tech Stack:** Python, TOML, pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-config-version-suffix-design.md`

## Global Constraints

- The config version is `2.2.0-sla`.
- The app/package version remains unchanged.
- Migration preserves shared config values and adds new fields from the fork template.

## Review Focus

- An upstream `2.2.0` config without fork fields triggers migration: cover with `test_config_file_update`.
- Migration preserves existing shared settings and supplies playlist defaults: assert in `test_config_file_update`.
- The version test accepts the `-sla` suffix while still checking the package version: cover with `tests/test_versions.py`.

---

### Task 1: Mark and migrate fork configs

**Files:**
- Modify: `streamrip/config.py` — set `CURRENT_CONFIG_VERSION`.
- Modify: `streamrip/config.toml` — set the bundled template's `[misc].version`.
- Modify: `tests/test_config.toml` — keep the sample config aligned with the fork version.
- Modify: `tests/test_config_old.toml` — model an upstream `2.2.0` config lacking fork fields.
- Modify: `tests/test_config.py` — assert migration version, preserved values, and fork-field defaults.
- Modify: `tests/test_versions.py` — accept a hyphenated suffix in config versions.

**Interfaces:**
- Consumes: `Config._update_file(old_path, new_path)` and the existing shared-key migration behavior.
- Produces: `CURRENT_CONFIG_VERSION == "2.2.0-sla"`; matching bundled/sample config versions; migration of `2.2.0` configs to the fork template.

- [ ] **Step 1: Add regression assertions**

Update `tests/test_config_old.toml` to use version `2.2.0`. In `test_config_file_update`, assert the resulting `[misc].version` is `2.2.0-sla`, existing shared values such as `downloads.folder` are retained, and `filepaths.playlist_format` / `filepaths.m3u8_format` receive the template values.

Update `tests/test_versions.py`'s version regex to accept an optional `-` suffix while retaining the existing package-version consistency assertion.

- [ ] **Step 2: Run the focused tests and confirm the regression**

Run: `pytest tests/test_config.py::test_config_file_update tests/test_versions.py -q`

Expected: FAIL because the migration still writes `2.2.0` instead of `2.2.0-sla`.

- [ ] **Step 3: Implement the config version**

Set `CURRENT_CONFIG_VERSION` in `streamrip/config.py` and `[misc].version` in `streamrip/config.toml` and `tests/test_config.toml` to `2.2.0-sla`. Leave `pyproject.toml` and `streamrip/__init__.py` versions unchanged.

- [ ] **Step 4: Run focused config tests**

Run: `pytest tests/test_config.py tests/test_versions.py -q`

Expected: PASS, including migration of the upstream-version fixture with shared values retained and new fork fields populated.
