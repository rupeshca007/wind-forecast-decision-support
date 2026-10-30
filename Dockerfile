FROM node:20-alpine AS frontend-build

WORKDIR /src

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY scripts scripts
COPY data data
COPY --from=frontend-build /src/dist /app/frontend_dist

ENV FRONTEND_DIST_PATH=/app/frontend_dist
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["sh", "-c", "if [ ! -f data/processed/january_2026.csv ]; then python scripts/fetch_january_2026.py; fi; exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
