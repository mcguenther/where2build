#!/usr/bin/env bash
# Put whatever extra certificate authority this machine terminates TLS with
# into the two build contexts, so `docker compose build` works here.
#
# Does nothing on a machine with direct internet access: there is no such
# bundle, the `ca/` directories stay empty, and both Dockerfiles skip the step
# that reads them. Safe to run always, and safe to run twice.
#
# The route is the one the Claude Code proxy's own documentation gives for
# containers: "copy /root/.ccr/ca-bundle.crt into the build context and install
# it in an early layer". A build container cannot reach the host's proxy and
# does not trust its CA, so this is the only thing that makes a fresh
# `pip install` or `npm ci` inside one succeed.
set -euo pipefail
cd "$(dirname "$0")/.."

# Where such a bundle is found, most specific first. CCR_CA_BUNDLE wins so a
# different environment can name its own.
CANDIDATES=(
  "${CCR_CA_BUNDLE:-}"
  /root/.ccr/ca-bundle.crt
  "$HOME/.ccr/ca-bundle.crt"
  /usr/local/share/ca-certificates/proxy-ca.crt
)

bundle=""
for candidate in "${CANDIDATES[@]}"; do
  if [ -n "$candidate" ] && [ -f "$candidate" ]; then
    bundle="$candidate"
    break
  fi
done

for context in backend frontend; do
  rm -f "$context/ca/build-ca.crt"
done

if [ -z "$bundle" ]; then
  echo "Keine zusätzliche CA gefunden — der Build braucht hier keine."
  exit 0
fi

for context in backend frontend; do
  mkdir -p "$context/ca"
  cp "$bundle" "$context/ca/build-ca.crt"
done
echo "CA aus $bundle in backend/ca und frontend/ca gelegt."
