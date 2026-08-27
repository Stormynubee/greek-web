# greek-web Supabase migration

This directory holds the Supabase-side artifacts for the greek-web re-architecture
(see `~/.commandcode/plans/greek-web-supabase-architectural-revamp.md`).

## Layout

```
supabase/
  config.toml                      # supabase init output
  migrations/
    20260101000000_init_greek_web.sql   # schema, RLS, RPCs, admin allowlist seed
  functions/
    assign-admin-role/index.ts     # Auth hook: writes app_metadata.role for the 3 admins
    chat-award-receiver/index.ts   # HTTP receiver greek-bingo POSTs to for chat points
  scripts/
    backfill.py                    # MongoDB Atlas -> Supabase backfill + invariant checks
```

## Phase 0 — Provision + push (run after the user creates the cloud project)

```sh
# One-time, on the operator's machine:
supabase login
supabase link --project-ref <ref>

# Apply the migration (this creates the schema, RLS, RPCs, app_admins seed).
supabase db push

# Deploy the two Edge Functions.
supabase functions deploy assign-admin-role --no-verify-jwt
supabase functions deploy chat-award-receiver --no-verify-jwt

# Set Edge Function env vars.
# CHAT_AWARD_SECRET must match the value the greek-bingo backend uses for
# its INTERNAL_POINTS_SECRET today.
supabase secrets set CHAT_AWARD_SECRET=...
# SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set automatically.

# Wire the assign-admin-role hook:
#   In Supabase dashboard: Authentication -> Hooks -> Custom Access Token Hook
#   -> Enable, select "assign-admin-role" function, save.
```

Then in the Discord Developer Portal, add the Supabase callback URL to your Discord
OAuth app's redirect allowlist:

```
https://<project-ref>.supabase.co/auth/v1/callback
```

## Phase 2 — Validate (no live writes yet)

The backfill script reads from MongoDB Atlas (the live DB) and the Supabase Postgres
side-by-side. It checks the critical invariant `SUM(ledger.delta) == profiles.points_balance`
and FK orphans BEFORE any flip. Use the same MONGO_URL your greek-web API already uses.

```sh
export MONGO_URL='mongodb+srv://...'
export SUPABASE_URL='https://<ref>.supabase.co'
export SUPABASE_SERVICE_ROLE_KEY='eyJ...'
pip install pymongo supabase
python supabase/scripts/backfill.py --validate-only
```

A non-zero exit code means there's drift that must be investigated before the
writes flip in Phase 4. The script is read-only in this mode and safe to run on
production data.

## Phase 4 — Flip writes (the only phase that breaks live)

The backend FastAPI data layer switches to Supabase behind a `DATA_STORE=postgres`
toggle. The backfill `--copy` mode writes the migrated rows. The reconciliation
job (not in this repo yet — Phase 4 deliverable) compares both stores for 24-48h
after the flip.

## Phase 5 — Frontend swaps to Supabase Auth

The frontend's `AuthContext.jsx` and `lib/api.js` are rewritten to use
`@supabase/supabase-js`. The `/admin/login` password form is removed. The
stream-games console sends the Supabase token to greek-bingo, which validates it
server-side. See the migration plan for the exact files.
