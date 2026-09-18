# Build the app, then serve the built files. Node does not appear in the final
# image: what ships is static files and nginx, which also proxies /api so the
# browser only ever sees one origin.
FROM node:22-alpine AS build
WORKDIR /app

# Extra certificate authorities for the build, and nothing on a normal machine.
# Node ships its own CA list and ignores the system trust store entirely, so
# `NODE_EXTRA_CA_CERTS` is the only thing that reaches it. The directory is
# copied rather than a glob: `COPY ca/*.crt` fails the build outright when
# there is nothing to match, and empty has to be the normal case. See
# `frontend/ca/README.md`.
COPY ca/ /build-ca/

# npm ci needs both, and only these two invalidate the dependency layer.
COPY package.json package-lock.json ./
RUN set -eu; \
    if ls /build-ca/*.crt >/dev/null 2>&1; then \
      cat /build-ca/*.crt > /tmp/build-ca.crt; \
      export NODE_EXTRA_CA_CERTS=/tmp/build-ca.crt; \
    fi; \
    npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
