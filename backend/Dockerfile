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
    # The two indexes built from open data sit on a volume of their own, not
    # under /app/data: that folder is the image's, and the Gemarkung directory
    # in it must follow the image rather than whatever a volume kept.
    NEARBY_POI_INDEX_PATH=/indexes/poi-sachsen.json \
    ADDRESSES_INDEX_PATH=/indexes/hauskoordinaten-sachsen.json.gz

WORKDIR /app

# Extra certificate authorities for the build, and nothing on a normal machine:
# `ca/` holds a README and whatever `scripts/setup-build-ca.sh` put next to it.
# An environment that re-terminates outbound TLS through its own CA — the cloud
# sandbox this is developed in, a corporate proxy — otherwise fails every
# `pip install` here with "self-signed certificate in certificate chain", and
# pip does not read the system trust store, so pointing it at the bundle is the
# only thing that works.
#
# The directory is copied rather than a glob: `COPY ca/*.crt` fails the build
# outright when there is nothing to match, and *empty is the normal case*.
#
# It goes to a path of its own, not into the system trust store: this is a
# single-stage build, so anything written there would ship. A build-time proxy
# CA has no business in the image that runs on somebody's server.
COPY ca/ /build-ca/

# Dependencies first: the sources change far more often than pyproject.toml, so
# this layer survives most rebuilds.
COPY pyproject.toml ./
# Two system dependencies, both invisible to pip.
#
# osmium links against expat at runtime and the slim image does not carry it:
# the wheel installs cleanly and then fails on import with
# "libexpat.so.1: cannot open shared object file", which looks like a broken
# package rather than a missing system library.
#
# Tesseract is the reader for a listing's attached cadastral extract, and the
# German language data is not optional either -- the patterns key on the words
# around the number ("Flurstück", "Gemarkung"), which the default English model
# does not produce. Without both, /api/health reports the channel as missing
# and every search runs on the listing's text alone, which is what "keine
# Bilderkennung eingerichtet" was saying.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libexpat1 \
      tesseract-ocr \
      tesseract-ocr-deu \
 && rm -rf /var/lib/apt/lists/*

# "poi" brings osmium, which only the index build needs — but the scheduler
# runs that build from this image, so leaving it out makes that job fail on an
# import nobody can fix from outside the container. "ocr" brings Pillow, which
# does the upscale that the measurements say buys the most.
# The certificates, where there are any — for this one command and no longer.
# `/build-ca` goes away in the same layer, so neither the bundle nor the README
# beside it reaches the final image.
#
# Three statements and an import check, not one `&&` chain ending in `rm`.
# Measured 18.09.2026: written as
# `pip install … && pip uninstall …; rm -rf …`, a failed install left `rm`'s
# zero as the layer's exit status — the build reported success and shipped a
# 350 MB image with no fastapi in it. An exit code is not a check; the import
# is.
RUN set -eux; \
    if ls /build-ca/*.crt >/dev/null 2>&1; then \
      cat /build-ca/*.crt > /tmp/build-ca.crt; \
      export PIP_CERT=/tmp/build-ca.crt REQUESTS_CA_BUNDLE=/tmp/build-ca.crt \
             SSL_CERT_FILE=/tmp/build-ca.crt; \
    fi; \
    pip install --no-cache-dir ".[poi,ocr]"; \
    pip uninstall -y where2build-backend; \
    rm -rf /build-ca /tmp/build-ca.crt; \
    python -c "import fastapi, shapely, pyproj, PIL"

COPY app ./app
# The scheduler runs these, and it runs from this same image — the jobs are
# the build scripts, so leaving them out makes the scheduler an empty shell.
COPY scripts ./scripts
# The committed Gemarkung directory travels in the image, so the container is
# complete on its own. Compose mounts the same folder over it read-only, which
# is how a POI index built afterwards gets in without a rebuild.
COPY data ./data

# The cache is written at runtime; the volume is mounted over it.
# /state belongs to the scheduler and holds one small record per job, /indexes
# holds the POI and address indexes, /data-input the routing inputs MOTIS is
# built from. All are volume mount points: created here so they carry the right
# owner, because a volume mounted over a path the image does not know arrives
# owned by root and the unprivileged process cannot write to it.
RUN useradd --system --uid 10001 app \
 && mkdir -p /cache /state /indexes /data-input \
 && chown -R app:app /cache /state /indexes /data-input
USER app

EXPOSE 8000

# One worker: every upstream already has its own concurrency limit, and a
# second worker would keep a second disk cache of the same answers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
