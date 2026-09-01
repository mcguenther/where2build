# The backend is a proxy and a disk cache in front of the official services.
# It owns no database — pyproj and shapely ship manylinux wheels, so there is
# nothing to compile and no build stage to keep out of the final image.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # Absolute: uvicorn's working directory is not the repository root here,
    # and a relative cache path would follow it.
    APP_CACHE_DIR=/cache \
    NEARBY_POI_INDEX_PATH=/app/data/poi-sachsen.json

WORKDIR /app

# Dependencies first: the sources change far more often than pyproject.toml, so
# this layer survives most rebuilds.
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip uninstall -y where2build-backend

COPY app ./app
# The committed Gemarkung directory travels in the image, so the container is
# complete on its own. Compose mounts the same folder over it read-only, which
# is how a POI index built afterwards gets in without a rebuild.
COPY data ./data

# The cache is written at runtime; the volume is mounted over it.
RUN useradd --system --uid 10001 app \
 && mkdir -p /cache \
 && chown -R app:app /cache
USER app

EXPOSE 8000

# One worker: every upstream already has its own concurrency limit, and a
# second worker would keep a second disk cache of the same answers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
