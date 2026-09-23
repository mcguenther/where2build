# Extra CA certificates for the build

Empty on a normal machine, and the build behaves exactly as if this directory
were not here.

It exists for environments that re-terminate outbound TLS through their own
certificate authority — the Claude Code cloud sandbox is one, and a corporate
proxy is another. There, `pip install` inside a fresh build container fails
with *self-signed certificate in certificate chain*, because pip does not read
the system trust store and the container cannot reach the host's proxy anyway.

The fix the proxy's own documentation gives is to **copy the CA into the build
context and install it in an early layer**, which is what the `COPY ca/`
in `backend/Dockerfile` does. Drop any number of `*.crt` files in here and they
are trusted for the duration of the build; they never reach the final image.

`scripts/setup-build-ca.sh` fills this directory automatically wherever it can
find such a bundle, and does nothing where it cannot.
