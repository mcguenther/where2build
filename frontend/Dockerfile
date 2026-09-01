# Build the app, then serve the built files. Node does not appear in the final
# image: what ships is static files and nginx, which also proxies /api so the
# browser only ever sees one origin.
FROM node:22-alpine AS build
WORKDIR /app

# npm ci needs both, and only these two invalidate the dependency layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
