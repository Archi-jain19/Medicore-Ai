# syntax=docker/dockerfile:1.7
# Production image for the MediCore AI web app: static SPA served by unprivileged nginx, with /api proxied
# to the backend (same origin, no CORS).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Empty = same-origin "/api". Only set this when the API lives on a different origin.
ARG VITE_API_BASE_URL=""
# Shown on the Help, Privacy and Terms pages when set (nothing is shown, and nothing invented, when empty)
ARG VITE_OPERATOR_NAME=""
ARG VITE_SUPPORT_EMAIL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL VITE_OPERATOR_NAME=$VITE_OPERATOR_NAME VITE_SUPPORT_EMAIL=$VITE_SUPPORT_EMAIL
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
ENV API_UPSTREAM=api:8000 CSP_CONNECT_EXTRA="" NGINX_ENVSUBST_FILTER="^(API_UPSTREAM|CSP_CONNECT_EXTRA)$"
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
