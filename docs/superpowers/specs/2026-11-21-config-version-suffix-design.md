# Config Version Suffix Design

## Intent

Distinguish Streamrip's fork-specific config from upstream config and ensure
existing configs are migrated when the fork adds required config fields.

## Approaches

- **Append `-sla` to the config version (chosen):** Reuse the existing exact
  version check and migration path. This also distinguishes the fork config.
- **Add a separate flavor field:** This would need new parsing and
  compatibility behavior, and would not trigger the current migration by itself.

## Design

Set the config version to `2.2.0-sla` in both `CURRENT_CONFIG_VERSION` and the
bundled config template. Leave the app/package version unchanged. Update the
version test pattern to accept the suffix and add a focused regression test
showing that an upstream-version config is migrated, shared user settings are
preserved, and fork-specific fields receive template defaults.

## Scope and constraints

This changes only config identification and migration coverage. Switching to
upstream may discard fork-only config values because upstream's template does
not include those keys. No unrelated config behavior is changed.
