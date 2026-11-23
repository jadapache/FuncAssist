FROM node:24-bookworm-slim AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm ci --prefix frontend
COPY frontend/ ./frontend/
ARG VITE_API_BASE=
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build --prefix frontend
FROM nginx:1.29-alpine
# HTTP or HTTPS is decided at start-up by 40-funcassist-tls.sh: HTTPS when a certificate is
# mounted in /etc/nginx/certs (tls.crt + tls.key), plain HTTP otherwise. See docs/DEPLOY_HTTPS.md.
COPY docker/nginx/ /etc/nginx/funcassist/
RUN sed -i 's/\r$//' /etc/nginx/funcassist/* \
    && mv /etc/nginx/funcassist/40-funcassist-tls.sh /docker-entrypoint.d/40-funcassist-tls.sh \
    && chmod +x /docker-entrypoint.d/40-funcassist-tls.sh \
    && cp /etc/nginx/funcassist/http.conf /etc/nginx/conf.d/default.conf \
    && mkdir -p /etc/nginx/certs
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80 443
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1/healthz || exit 1
