# Railway API + Vercel frontend

This project deploys as two services:

```text
Browser → Vercel React SPA → Railway FastAPI API → MongoDB Atlas
```

Do not create production secrets until the local Docker MongoDB smoke suite
passes.

## Railway

Create a Railway service from this repository and set its root directory to
`backend/`. Railway will use `backend/railway.toml`; the equivalent start
command is:

```text
python -m uvicorn server:app --host 0.0.0.0 --port $PORT
```

Set these variables in Railway:

```text
APP_ENV=production
MONGO_URL=mongodb+srv://...
DB_NAME=greekgodberry
DISCORD_CLIENT_ID=...
DISCORD_CLIENT_SECRET=...
DISCORD_REDIRECT_URI=https://<railway-domain>/api/auth/discord/callback
FRONTEND_URL=https://<vercel-domain>
LOCKLY_API_BASE=https://...
LOCKLY_API_KEY=...
JWT_SECRET=<random-secret>
ADMIN_JWT_SECRET=<different-random-secret>
OWNER_EMAIL=...
ADMIN_USERNAME=...
ADMIN_PASSWORD=<strong-password>
CORS_ORIGINS=https://<vercel-domain>,https://<custom-frontend-domain>
COOKIE_SECURE=true
COOKIE_SAMESITE=none
TRUST_PROXY_HEADERS=true
```

`MONGO_URL` must point to MongoDB Atlas or another replica-set deployment.
The API health check is:

```text
https://<railway-domain>/api/health
```

## Vercel

Import the repository as a Vercel project and set the project root directory
to `frontend/`. The committed `frontend/vercel.json` configures the CRA build
output and React Router fallback.

Set this variable separately in each Vercel environment:

```text
REACT_APP_BACKEND_URL=https://<railway-domain>
```

- Preview: use the Railway preview API URL and the exact Vercel preview origin
  in Railway `CORS_ORIGINS`.
- Production: use the Railway production API URL and the exact production
  Vercel/custom-domain origins in Railway `CORS_ORIGINS`.

Because CRA embeds `REACT_APP_BACKEND_URL` at build time, redeploy after
changing it.

## Discord callback order

1. Create/deploy the Railway API and copy its stable public domain.
2. Add `https://<railway-domain>/api/auth/discord/callback` to the Discord
   application's OAuth2 redirect URLs.
3. Configure Railway `FRONTEND_URL`, `CORS_ORIGINS`, cookie settings, and
   secrets.
4. Verify `GET /api/health` and `GET /api/auth/discord/login`.
5. Deploy the Vercel frontend with `REACT_APP_BACKEND_URL`.
6. Add any Vercel preview/custom domains to the exact CORS list before testing
   browser cookies.

Never use `CORS_ORIGINS=*` with credentialed cookies, and never commit either
`.env` file.
