# GreekGodBerry Community

GreekGodBerry is a React community frontend backed by a FastAPI API and MongoDB.

## Architecture

- `frontend/` — Create React App + CRACO frontend
- `backend/` — FastAPI API, Discord OAuth, admin auth, points, games, giveaways, and Lockly proxy
- Local MongoDB — Docker Compose single-node replica set so transaction paths match production
- Production target — Vercel frontend, Railway API, MongoDB Atlas

## Local setup

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker Desktop
- Discord and Lockly credentials for authenticated/external flows

### 1. Install dependencies

```powershell
cd frontend
npm install --legacy-peer-deps
cd ..
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
```

### 2. Configure environment

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

Replace the placeholder secrets in both files. Keep `COOKIE_SECURE=false` and
`COOKIE_SAMESITE=lax` for local HTTP development.

### 3. Start MongoDB

```powershell
docker compose up -d mongo mongo-init
```

Wait for the replica set initialization to finish before starting the API.

### 4. Start the API

```powershell
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Verify it:

```powershell
Invoke-WebRequest http://localhost:8000/api/health
```

### 5. Start the frontend

```powershell
cd frontend
npm start
```

Open <http://localhost:3000>.

## Tests

With MongoDB and the API running:

```powershell
python -m pytest backend\tests -n 0
cd frontend
npm run build
```

The backend integration tests use the configured API and MongoDB through
`BACKEND_API_URL`, `MONGO_URL`, and the other backend environment variables.

## Deployment

### Railway API

Deploy the repository with the service root set to `backend/` and the start
command:

```text
python -m uvicorn server:app --host 0.0.0.0 --port $PORT
```

Set the production backend variables from `backend/.env.example`. Use the
MongoDB Atlas connection string with replica-set support, set
`COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, `TRUST_PROXY_HEADERS=true`, and
set `CORS_ORIGINS` to the exact Vercel and custom frontend origins.

### Vercel frontend

Set the Vercel project root directory to `frontend/`, build with `npm run build`,
and serve the `build/` directory. Set `REACT_APP_BACKEND_URL` separately for
Preview and Production. The frontend `vercel.json` supplies the React Router
fallback for direct navigation.

Update the Discord application's OAuth redirect URI to:

```text
https://<railway-api-domain>/api/auth/discord/callback
```

Never commit `.env` files, credentials, JWT secrets, or database connection
strings.
