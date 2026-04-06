# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY streamrip/ ./streamrip/
COPY backend/ ./backend/
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --only main --no-interaction && pip install --no-cache-dir websockets
COPY --from=frontend /app/frontend/build ./backend/static/
EXPOSE 8080
CMD ["uvicorn", "backend.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
