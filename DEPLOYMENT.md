# Railway API + Vercel frontend

The deployment has two services and one database:

```text
Browser → Vercel React SPA → Railway FastAPI API → MongoDB Atlas
```

The frontend receives only the public API origin. Discord secrets, the Lockly
key, admin password, and both JWT signing secrets stay in Railway/local secret
stores and are never embedded in the React build.

## Release security gate

The credentials previously pasted during development are compromised. Do not
reuse, commit, log, test with, or place them in an environment example.
Before production:

1. Rotate the Discord client secret in the Discord Developer Portal.
2. Revoke and reissue the Lockly API key.
3. Change the admin password.
4. Generate independent random values for `JWT_SECRET` and
   `ADMIN_JWT_SECRET`.
5. Store the replacements only in Railway variables or a local secret store.

The API refuses `APP_ENV=production` or `APP_ENV=staging` when placeholder
values remain, when the Lockly base is incorrect, or when production cookies
are not secure. A deployment using placeholders is intentionally not a release.

## Railway

Create a Railway service from this repository with root directory `backend/`.
Railway uses `backend/railway.toml`:

```text
python -m uvicorn server:app --host 0.0.0.0 --port $PORT
```

Configure these variables in Railway. Values marked `<...>` are placeholders
for the deployment dashboard only; do not copy development secrets into them.

```text
APP_ENV=production
MONGO_URL=mongodb+srv://<user>:<password>@<cluster>/<db>?retryWrites=true&w=majority
DB_NAME=greekgodberry
DISCORD_CLIENT_ID=<discord-client-id>
DISCORD_CLIENT_SECRET=<rotated-discord-client-secret>
DISCORD_REDIRECT_URI=https://<railway-domain>/api/auth/discord/callback
FRONTEND_URL=https://<vercel-production-domain>
LOCKLY_API_BASE=https://public-api.lockly.io/api/public/streamer
LOCKLY_API_KEY=<rotated-lockly-api-key>
JWT_SECRET=<random-user-session-secret>
ADMIN_JWT_SECRET=<different-random-admin-session-secret>
OWNER_EMAIL=<owner-email>
ADMIN_USERNAME=<admin-username>
ADMIN_PASSWORD=<new-strong-admin-password>
CORS_ORIGINS=https://<vercel-production-domain>,https://<custom-frontend-domain>
COOKIE_SECURE=true
COOKIE_SAMESITE=none
TRUST_PROXY_HEADERS=true
```

`MONGO_URL` must point to MongoDB Atlas or another replica-set deployment;
transactions and unique-entry guarantees depend on that. Verify:

```text
https://<railway-domain>/api/health
```

Railway preview environments must use a separate database/secret set and
their exact frontend origin in `CORS_ORIGINS`. Never use `*` with credentialed
cookies.

## Vercel

Import the repository as a Vercel project with root directory `frontend/`.
The committed `frontend/vercel.json` configures the CRA build, SPA fallback,
and immutable caching for hashed files.

Set this variable separately in each Vercel environment:

```text
REACT_APP_BACKEND_URL=https://<railway-domain>
```

Use the Railway preview API plus the exact Vercel preview origin for Preview,
and the Railway production API plus exact production/custom origins for
Production. CRA embeds this value at build time, so redeploy after changing it.
The intentional frontend package-manager path is npm with
`frontend/package-lock.json`; use `npm ci` for reproducible installs.

## Discord callback order

1. Deploy the Railway API and copy its stable public domain.
2. Register only
   `https://<railway-domain>/api/auth/discord/callback` in Discord OAuth2.
   The Vercel SPA is not the callback and must never receive the client secret.
3. Provision rotated Railway secrets, `FRONTEND_URL`, exact `CORS_ORIGINS`, and
   secure cookie settings.
4. Verify `/api/health` and `/api/auth/discord/login`.
5. Deploy Vercel with `REACT_APP_BACKEND_URL`.
6. Verify Discord login, cookie attributes, protected actions, Lockly data,
   and direct refreshes on every SPA route.

Never commit `.env` files, credentials, JWT secrets, database connection
strings, or production build output.
