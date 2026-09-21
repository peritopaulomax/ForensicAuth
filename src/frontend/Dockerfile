# Multi-stage build for ForensicAuth frontend

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve with nginx (TLS on 443; HTTP 80 redirects to HTTPS)
FROM nginx:alpine

RUN apk add --no-cache openssl

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint-forensicauth.sh
RUN chmod +x /docker-entrypoint-forensicauth.sh

EXPOSE 80 443

CMD ["/docker-entrypoint-forensicauth.sh"]
