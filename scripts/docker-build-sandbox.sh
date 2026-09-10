#!/usr/bin/env bash
# Builds and runs the Compose stack in the Claude Code cloud sandbox, where a
# transparent TLS-reterminating proxy makes any HTTPS install inside a fresh
# build container fail with "self-signed certificate in certificate chain" --
# reproduced for both `pip install` and `npm ci`. See CLAUDE.md, "Traps that
# already cost time". On a normal machine with direct internet access there
# is no such proxy, the CA bundle this script looks for does not exist, and
# it falls back to a plain `docker compose` call.
#
# The two Dockerfiles are never modified: BuildKit's `--build-context` names
# the sandbox's CA directory as an extra build stage, and a patched copy of
# each Dockerfile (built with `sed`, from a temp file) is the only thing that
# references it -- so a normal build stays exactly the committed Dockerfile.
#
# Usage:
#   scripts/docker-build-sandbox.sh build   # docker compose build, patched
#   scripts/docker-build-sandbox.sh up      # build, then docker compose up -d
#   scripts/docker-build-sandbox.sh <args>  # anything else: plain `docker compose <args>`
set -euo pipefail
cd "$(dirname "$0")/.."

CA_BUNDLE="${CCR_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}"

build_patched() {
  local ca_dir ca_file tmp backend_image frontend_image
  ca_dir="$(dirname "$CA_BUNDLE")"
  ca_file="$(basename "$CA_BUNDLE")"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  # pip does not read the system trust store; point it at the bundle directly.
  sed "/^RUN pip install --no-cache-dir \".\[poi,ocr\]\"/i\\
COPY --from=cacerts ${ca_file} /tmp/ccr-ca.crt\\
ENV PIP_CERT=/tmp/ccr-ca.crt REQUESTS_CA_BUNDLE=/tmp/ccr-ca.crt SSL_CERT_FILE=/tmp/ccr-ca.crt" \
    backend/Dockerfile > "$tmp/backend.Dockerfile"

  # Node ships its own CA list too and ignores the system store the same way.
  sed "/^COPY package.json package-lock.json \.\/\$/i\\
COPY --from=cacerts ${ca_file} /tmp/ccr-ca.crt\\
ENV NODE_EXTRA_CA_CERTS=/tmp/ccr-ca.crt" \
    frontend/Dockerfile > "$tmp/frontend.Dockerfile"

  # `docker compose config --images <service>` pulls in dependencies too on
  # this Compose version (frontend depends_on backend), so it is not a
  # reliable per-service filter. Neither service sets an explicit `image:`,
  # so Compose's own default -- "<project name>-<service>" -- is what a plain
  # `docker compose build` would tag anyway.
  local project
  project="$(docker compose config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["name"])')"
  backend_image="${project}-backend"
  frontend_image="${project}-frontend"

  docker build --build-context cacerts="$ca_dir" -f "$tmp/backend.Dockerfile" -t "$backend_image" ./backend
  docker build --build-context cacerts="$ca_dir" -f "$tmp/frontend.Dockerfile" -t "$frontend_image" ./frontend
}

if [ ! -f "$CA_BUNDLE" ]; then
  exec docker compose "$@"
fi

case "${1:-build}" in
  build)
    build_patched
    ;;
  up)
    build_patched
    shift
    docker compose up "$@"
    ;;
  *)
    exec docker compose "$@"
    ;;
esac
