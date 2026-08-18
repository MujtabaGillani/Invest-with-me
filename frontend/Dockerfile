# Frontend image.
#
# The build produces static files, so the runtime stage is just nginx - no Node in
# the shipped image at all.
#
# Note that VITE_ variables are baked in at BUILD time, not read at runtime: Vite
# performs a textual substitution during the build. That is why the API base URL
# defaults to a relative path and nginx proxies it, rather than the image being
# rebuilt per environment.

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

# Lock file first: this layer only rebuilds when dependencies change.
COPY package.json package-lock.json ./
# `npm ci` installs exactly the lock file and fails if it has drifted from
# package.json - the right behaviour for a reproducible build.
RUN npm ci

COPY tsconfig*.json vite.config.ts index.html openapi.json ./
COPY src ./src

# `vite build` rather than `npm run build`: the npm script also runs `tsc --build`,
# and type checking belongs in CI where a failure is reported as a failure. Doing it
# here would mean a type error surfaces as an opaque image build failure.
RUN npx vite build

# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
