# syntax=docker/dockerfile:1
#
# Build: docker build -f network-ui.Dockerfile -t netops-frontend:local .
# (build context must be the repo root)
#
# KNOWN GAP, read before deploying anywhere but local Docker testing: network-ui/src/App.jsx
# hardcodes `const DJANGO_URL = "http://localhost:8000/api"`. For local `docker run` testing
# this works fine -- the fetch() calls run in your browser on the host, not inside the
# container, so "localhost:8000" correctly resolves to the backend container's mapped port.
# It will NOT work once this image is actually deployed into infrastructure-simulation/ (a
# user's browser hitting the frontend Pod has no route to "localhost:8000" for the backend
# Service) -- that's the same gap already disclosed in README.md's Production-readiness
# checklist ("Ingress/TLS ... not yet ported"). Not fixed here since it's a real behavior
# change to App.jsx, not a Dockerfile concern -- say the word if you want that addressed.

# ---- Stage 1: build the static bundle ----
# Node version pinned here is a reasonable LTS choice, NOT verified against your local
# toolchain -- there's no .nvmrc/engines field in package.json to match against. Bump this
# if your local `npm run build` uses a different major version.
FROM node:22-alpine AS builder

WORKDIR /build

COPY network-ui/package.json network-ui/package-lock.json* ./
RUN npm ci

# Vite bakes VITE_-prefixed env vars into the bundle AT BUILD TIME (not read at container
# startup -- see the top-of-file note on why that matters for deploying this image anywhere
# but local testing). Nothing in network-ui/ supplies VITE_API_URL automatically -- no
# .env/.env.production exists, .env.example is a template Vite never auto-loads, and
# .dockerignore excludes .env* from the build context anyway -- so without this ARG, Vite
# bakes in `undefined` and every API call in the shipped app silently breaks.
# Build with: docker build -f network-ui.Dockerfile --build-arg VITE_API_URL=http://localhost:8000/api -t netops-frontend:local .
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}

COPY network-ui/ ./
RUN npm run build

# ---- Stage 2: serve the static build with a non-root nginx ----
# nginx-unprivileged runs as a non-root user (uid 101) and listens on 8080 by default,
# avoiding the usual "bind to port 80 needs root" problem with plain nginx:alpine.
FROM nginxinc/nginx-unprivileged:alpine AS runtime

COPY network-ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ > /dev/null || exit 1
