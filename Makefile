.PHONY: test test-unit test-e2e test-all build-frontend build-docker dev lint

# Run unit tests (no credentials needed)
test:
	poetry run pytest tests/ -q --tb=short --ignore=tests/test_e2e_download.py -k "not test_streamrip_versions_match"

# Run unit tests with verbose output
test-unit:
	poetry run pytest tests/ -v --tb=short --ignore=tests/test_e2e_download.py -k "not test_streamrip_versions_match"

# Run e2e tests (requires QOBUZ_TOKEN and QOBUZ_USER_ID env vars)
test-e2e:
	poetry run pytest tests/test_e2e_download.py -v --tb=short

# Run everything
test-all:
	poetry run pytest tests/ -v --tb=short -k "not test_streamrip_versions_match"

# Build frontend
build-frontend:
	cd frontend && npm run build

# Build Docker image
build-docker:
	docker build -f docker/Dockerfile -t streamrip .

# Run Docker container
run-docker:
	docker run -p 8080:8080 -v ~/Downloads/Music:/music -v streamrip-data:/data -e STREAMRIP_DB_PATH=/data/streamrip.db streamrip

# Build and run
docker: build-docker run-docker

# Local dev server (backend only)
dev:
	poetry run uvicorn backend.main:create_app --factory --port 8080 --reload

# Local dev server (frontend)
dev-frontend:
	cd frontend && npm run dev

# Lint
lint:
	poetry run ruff check streamrip/ backend/
