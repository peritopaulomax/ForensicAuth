# TLS for ForensicAuth frontend (option B)

Production terminates HTTPS **inside** the `frontend` nginx container.

## Generate a self-signed certificate

```bash
cd /opt/forensicauth
chmod +x scripts/generate_frontend_tls_cert.sh
./scripts/generate_frontend_tls_cert.sh labfaces02 10.61.229.231
```

Creates `tls.crt` and `tls.key` in this directory (gitignored).

## Configure CORS

In `.env.production` use the same hosts as HTTPS origins:

```bash
CORS_ORIGINS=["https://labfaces02","https://10.61.229.231"]
```

Restart the `app` container after changing CORS.

## Bring up / rebuild frontend

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.override.yml \
  --env-file .env.production up -d --build frontend
```

- Port **80**: redirects to `https://$host$request_uri`
- Port **443**: SPA + `/api/v1` proxy

Browsers will warn until clients trust `tls.crt` (import as trusted root/CA) or the user accepts the exception.

Workers on PROD-2/PROD-3 are unaffected (they use Redis, Postgres, and NFS — not this nginx).
