# Forge — single-image deploy (FastAPI serves the API + the built frontend).
# Build context is this folder (forge/).

# ---- 1. build the frontend ----
FROM node:20-bullseye-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build          # -> /fe/dist

# ---- 2. backend + serve ----
FROM python:3.11-slim-bullseye
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# system libraries OpenCASCADE / VTK (cadquery) need at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglu1-mesa libglib2.0-0 libxrender1 libxext6 libsm6 \
        libice6 libfontconfig1 libgomp1 libx11-6 libxi6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /fe/dist ./frontend_dist

# FastAPI serves the SPA from here; /data is the persistent disk (projects + db)
ENV FORGE_FRONTEND_DIST=/app/frontend_dist
ENV FORGE_DATA_DIR=/data
# small cloud instances (e.g. Render 512MB): one CAD process at a time, 1 drawing view
ENV FORGE_LOWMEM=1
EXPOSE 8000
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
