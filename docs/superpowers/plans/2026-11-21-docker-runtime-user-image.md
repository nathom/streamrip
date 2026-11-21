# Docker Runtime User and Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support runtime `PUID`/`PGID` and produce a smaller, faster-to-rebuild production image.

**Architecture:** Build the application and its production-only virtualenv in a builder stage, then copy the virtualenv into a matching Python/Alpine runtime stage. A small root entrypoint validates/defaults numeric IDs and uses `su-exec` to run Streamrip without changing ownership of bind mounts.

**Tech Stack:** Docker multi-stage builds, Alpine, Python 3.12, Poetry 2.5.2, POSIX shell, `su-exec`.

**Spec:** `docs/superpowers/specs/2026-11-21-docker-runtime-user-image-design.md`

## Global Constraints

- Use the same pinned `python:3.12-alpine@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89` base in builder and runtime stages.
- Install production dependencies only; keep Poetry and build tools out of the runtime stage.
- Use `/app/.venv` for the virtualenv and `/config` for runtime `HOME`.
- Default `PUID=1029` and `PGID=100` to preserve the existing Alpine identity.
- Do not chown bind-mounted `/music` or `/config`; those host paths must be accessible to the configured IDs.
- Keep the existing `/music` and `/config` mounts and Streamrip command; do not set Compose `user:`.
- Add `PUID` and `PGID` to the external file already referenced by Compose `env_file`; leave the Compose YAML unchanged.
- Do not run `apk upgrade` or copy unused `requirements*.txt` files into the image.

## Review Focus

- Missing IDs use the documented defaults; non-numeric IDs fail clearly instead of starting the application — test both in Task 1.
- Non-default IDs are the process UID/GID and can write to mounted paths that are accessible to those IDs — test in Task 1.
- Inaccessible host paths remain permission errors and are not silently changed by startup — verify in Task 1.
- Runtime Python dependencies have all required shared libraries — verify `rip --help` in Task 2.
- Source-only changes reuse the dependency-install layer, while the final image excludes Poetry and development dependencies — verify in Task 2.

---

### Task 1: Add runtime UID/GID startup and stable virtualenv

**Files:**
- Create: `docker-entrypoint.sh` — validate/default IDs, set `HOME`, and drop privileges.
- Modify: `Dockerfile` — install `su-exec`, configure the in-project virtualenv, and invoke the entrypoint as root.
- Modify: `shell/streamrip.sh` — activate `/app/.venv` directly.

**Interfaces:**
- Consumes: `PUID`, `PGID`, and the command/arguments passed to the image; defaults are `1029` and `100`.
- Produces: startup execution as the numeric `PUID:PGID`, with `HOME=/config`; the app virtualenv is available at `/app/.venv`.

- [ ] **Step 1: Build the current image and confirm the runtime-ID check fails**

Run the current Docker build, then run a container with `PUID=1234`, `PGID=2345`, and command `sh -c 'test "$(id -u)" = 1234 && test "$(id -g)" = 2345'`.

Expected: the check fails because the current image runs as its fixed Dockerfile user.

- [ ] **Step 2: Create `docker-entrypoint.sh`**

Use POSIX shell. Default the variables to `1029` and `100`, reject values containing non-digits with a diagnostic to stderr and a nonzero exit, set and export `HOME=/config`, then `exec su-exec "$PUID:$PGID" "$@"`. Do not create a named account or chown mounted paths.

- [ ] **Step 3: Configure the Dockerfile and Streamrip script for the stable virtualenv**

Install `su-exec` in the image. Set `POETRY_VIRTUALENVS_IN_PROJECT=true` before `poetry install`, keeping the existing build-time `Amadeus` user for that install. After installation, set `USER root`, `ENTRYPOINT ["/docker-entrypoint.sh"]`, and `CMD ["/streamrip.sh"]`. Add a `#!/bin/sh` shebang to `shell/streamrip.sh` and source `/app/.venv/bin/activate` instead of querying Poetry at runtime.

- [ ] **Step 4: Verify shell syntax and entrypoint behavior**

Run `sh -n docker-entrypoint.sh && sh -n shell/streamrip.sh` and `poetry run pytest tests/test_docker_entrypoint.py -q`. Defer the image build to Task 2 because the current `alpine:latest` base resolves to Python 3.14, where locked Pillow 10.4.0 attempts a source build and fails without zlib headers.

Expected: both scripts parse and all entrypoint tests pass.

- [ ] **Step 5: Verify UID/GID defaults and input validation**

Run the image with `PUID=1234`, `PGID=2345`, and command `sh -c 'test "$(id -u)" = 1234 && test "$(id -g)" = 2345 && test "$HOME" = /config'`. Repeat without either variable and assert IDs `1029:100`. Run with a non-numeric ID and assert the entrypoint exits nonzero before running the command.

Expected: configured IDs and defaults are honored; malformed IDs fail clearly.

- [ ] **Step 6: Verify bind-mount access behavior**

With temporary host directories owned by `1234:2345`, mount them at `/music` and `/config` and assert the process can create a file in each. Repeat with a root-owned directory that is inaccessible to `1234:2345`; assert the write fails and confirm the host directory ownership was not changed.

Expected: accessible mounts are writable, and inaccessible mounts are not silently chowned.

### Task 2: Build a production-only multi-stage image

**Files:**
- Modify: `Dockerfile` — split builder and runtime stages, minimize packages, and preserve dependency-layer caching.
- Create: `.dockerignore` — exclude repository and local build artifacts from the Docker context.

**Interfaces:**
- Consumes: `/app/.venv` and `docker-entrypoint.sh` from Task 1.
- Produces: a runtime image containing Python, the application virtualenv, required runtime libraries, `su-exec`, and startup scripts; no Poetry or development dependencies.

- [ ] **Step 1: Record the current image size**

Attempted the pre-optimization build, but it fails on the current `alpine:latest`/Python 3.14 base while building Pillow 10.4.0 because zlib headers are unavailable. Record that no valid baseline image size exists; compare the final runtime image with the builder stage instead.

- [ ] **Step 2: Split dependency and runtime installation**

Use the same pinned `python:3.12-alpine@sha256:c5ba3deef00c7758561a0f03c26f44f10589263d40e732b8748e0d1f38f6dd89` image in both stages. In the builder, install pinned Poetry `2.5.2` with pip cache disabled and add any build-only Alpine packages needed by locked dependencies. Copy `poetry.lock`, `pyproject.toml`, and `README.md` before application source; configure `/app/.venv`; run `poetry install --only main --no-root`; then copy `streamrip/` and run `poetry install --only-root`. Install only required runtime Alpine packages and `su-exec` in the final stage, and copy `/app/.venv`, `/app/streamrip`, `/streamrip.sh`, and `/docker-entrypoint.sh` from the builder. Poetry installs the project in editable mode, so the runtime source tree must remain at `/app/streamrip`.

- [ ] **Step 3: Remove redundant image inputs and package operations**

Remove `apk update`, `apk upgrade`, and `apk cache clean`; use `apk add --no-cache` for required packages. Remove `requirements.txt` and `requirements-dev.txt` from Docker `COPY` instructions. Add `.dockerignore` entries for `.git`, local virtualenvs, Python caches, test caches, and other files not required to build the application.

- [ ] **Step 4: Build and verify the final image**

Run `docker build -t streamrip:optimized .`, then run `docker run --rm streamrip:optimized /app/.venv/bin/rip --help`.

Expected: the command succeeds with no missing shared libraries; runtime checks still pass.

- [ ] **Step 5: Verify image contents and size**

Run `docker run --rm streamrip:optimized sh -c '! command -v poetry && ! test -e /app/.venv/bin/pytest'`, build the builder target as `streamrip:builder`, and compare `docker image inspect` sizes for `streamrip:optimized` and `streamrip:builder`.

Expected: the runtime image is smaller than the builder and contains no Poetry or development dependencies.

- [ ] **Step 6: Verify dependency-layer caching**

Make and then revert a temporary source-only change under `streamrip/`, rebuilding with `docker build --progress=plain -t streamrip:optimized .`.

Expected: the dependency-install layer is reported as cached.
