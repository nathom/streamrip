# Docker Runtime User and Image Design

## Intent

Run Streamrip with deployment-specific numeric UID/GID values from `PUID` and
`PGID`, while reducing the final Docker image and keeping routine rebuilds
efficient.

## Approaches

- **Multi-stage build (chosen):** Keep Poetry and build tools in a builder
  stage, and copy the production virtualenv into a matching runtime stage.
  This should give the smallest runtime image, with some care needed for
  native runtime libraries.
- **Single-stage cleanup:** Exclude development dependencies and avoid
  unnecessary package/cache installation. This is simpler, but leaves Poetry
  and build-time tools in the final image.

## Design

Use the same pinned Python/Alpine base in builder and runtime stages. Build
the application in `/app/.venv` with production dependencies only, and order
manifest/source copies so dependency installation can be cached across source
changes. The runtime stage contains Python, the virtualenv, required runtime
libraries, `su-exec`, and the startup scripts; it does not contain Poetry or
development dependencies.

The container starts as root only to validate/default `PUID` and `PGID`, set
`HOME=/config`, and then `exec` the requested command through `su-exec` using
the numeric IDs. `streamrip.sh` activates `/app/.venv` directly. Do not create
a named account or chown bind-mounted paths: the host paths must already be
accessible to the configured IDs.

Add `PUID` and `PGID` to the existing service `env_file`; no Compose YAML
change is needed. Do not set Compose `user:`, since that would bypass the
root entrypoint and `env_file` values are not Compose interpolation values.

## Scope and constraints

Keep the existing `/music` and `/config` mount points and application command.
Install only production dependencies, avoid `apk upgrade`, and avoid copying
unused requirements files into the image. Add `.dockerignore` entries for
repository/build artifacts that are not needed by Docker. Preserve Alpine
compatibility by verifying required shared libraries in the runtime stage.

## Acceptance criteria

- The image builds reproducibly from pinned, matching builder/runtime bases.
- Runtime process UID/GID match configured `PUID`/`PGID`; defaults preserve
  the current identity where practical.
- Streamrip can read its installed environment and write to accessible
  `/music` and `/config` mounts under a non-default UID/GID.
- The final image excludes Poetry and development dependencies.
- Dependency installation remains cached when only application source changes.
