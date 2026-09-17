#!/usr/bin/env bash
# The sandbox's Chromium answers ERR_CERT_AUTHORITY_INVALID to every https
# address because the agent proxy re-terminates TLS with a CA that only the
# shell trusts: the NSS store Chromium reads is created empty. Importing the
# bundle there is what gives the browser the same reach the shell has.
# Idempotent, and a no-op on a machine without the proxy.
set -euo pipefail

bundle=${CCR_CA_BUNDLE:-/root/.ccr/ca-bundle.crt}
db="${HOME}/.pki/nssdb"

if [ ! -f "$bundle" ]; then
  echo "Kein Agent-Proxy auf dieser Maschine ($bundle fehlt) — der Browser braucht hier nichts."
  exit 0
fi

if ! command -v certutil >/dev/null 2>&1; then
  echo "certutil fehlt, installiere libnss3-tools …"
  apt-get update -qq && apt-get install -y -qq libnss3-tools >/dev/null
fi

mkdir -p "$db"
[ -f "$db/cert9.db" ] || certutil -d "sql:$db" -N --empty-password

# A fresh import every time, so a rotated bundle does not leave a stale root
# behind and the script stays safe to re-run.
while certutil -d "sql:$db" -L | grep -q '^ccr-ca-'; do
  nick=$(certutil -d "sql:$db" -L | grep -m1 '^ccr-ca-' | awk '{print $1}')
  certutil -d "sql:$db" -D -n "$nick"
done

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
csplit -z -s -f "$work/ca-" -b "%03d.pem" "$bundle" '/-----BEGIN CERTIFICATE-----/' '{*}'

n=0
for pem in "$work"/ca-*.pem; do
  certutil -d "sql:$db" -A -t "C,," -n "ccr-ca-$n" -i "$pem"
  n=$((n + 1))
done

echo "$n Zertifikate in $db importiert — der Browser erreicht jetzt dieselben Hosts wie die Shell."
