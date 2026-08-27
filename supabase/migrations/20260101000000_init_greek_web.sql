-- greek-web Supabase Postgres schema (Phase 0 + Phase 1)
-- Migrated from MongoDB collections: users, ledger, rewards, stream_games, game_entries,
-- giveaways, giveaway_entries, custom_leaderboard, live_status. Admin allowlist
-- (app_admins) replaces the OWNER_EMAIL single-owner + ADMIN_DISCORD_IDS env approach.

-- =====================================================================
-- TABLES
-- =====================================================================

-- profiles: 1:1 with auth.users. discord_id is the public key we already use today.
create table public.profiles (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  discord_id     text unique not null,
  username       text not null,
  email          text,
  avatar_url     text,
  role           text not null default 'viewer' check (role in ('viewer','admin','owner')),
  points_balance bigint not null default 0,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now()
);
create index profiles_discord_id_idx on public.profiles(discord_id);
create index profiles_points_idx on public.profiles(points_balance desc);

-- ledger: append-only audit. balance_after is denormalized snapshot at write time.
-- idempotency_key is the atomic guard for chat-award / watch-beat / signup bonuses.
create table public.ledger (
  id              bigserial primary key,
  user_id         uuid not null references public.profiles(user_id) on delete restrict,
  delta           int not null,
  balance_after   bigint not null,
  reason          text not null,
  idempotency_key text unique,
  ref             text,
  ts              bigint not null default (extract(epoch from now())::bigint),
  created_at      timestamptz not null default now()
);
create index ledger_user_reason_ts_idx on public.ledger(user_id, reason, ts desc);
create index ledger_user_created_idx on public.ledger(user_id, created_at desc);

-- rewards: store items
create table public.rewards (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  description text not null,
  cost        int not null check (cost >= 0),
  stock       int not null, -- -1 means unlimited
  image_url   text,
  active      boolean not null default true,
  category    text not null default 'custom' check (category in ('custom','bonus','tip','vip')),
  requires    text, -- e.g. "Lockly username"
  created_at  timestamptz not null default now()
);
create index rewards_active_idx on public.rewards(active) where active = true;

-- stream_games: stream games catalog
create table public.stream_games (
  id              uuid primary key default gen_random_uuid(),
  title           text not null,
  kind            text not null,
  status          text not null default 'open' check (status in ('open','closed','resolved')),
  entry_cost      int not null default 0,
  reward_pool     int not null default 0,
  prompt          text,
  options         jsonb not null default '[]'::jsonb,
  winning_option  text,
  created_at      timestamptz not null default now(),
  resolved_at     timestamptz
);
create index stream_games_status_idx on public.stream_games(status);

-- game_entries: per-user game participation. UNIQUE(game, user) prevents double-join.
create table public.game_entries (
  id         uuid primary key default gen_random_uuid(),
  game_id    uuid not null references public.stream_games(id) on delete cascade,
  user_id    uuid not null references public.profiles(user_id) on delete cascade,
  choice     text,
  stake      int not null default 0,
  created_at timestamptz not null default now(),
  unique (game_id, user_id)
);
create index game_entries_user_idx on public.game_entries(user_id);

-- giveaways
create table public.giveaways (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  description text not null,
  prize       text not null,
  image_url   text,
  max_winners int not null default 1,
  status      text not null default 'open' check (status in ('open','drawn','closed')),
  ends_at     timestamptz,
  winners     jsonb not null default '[]'::jsonb,
  drawn_at    timestamptz,
  created_at  timestamptz not null default now()
);
create index giveaways_status_idx on public.giveaways(status);

create table public.giveaway_entries (
  id          uuid primary key default gen_random_uuid(),
  giveaway_id uuid not null references public.giveaways(id) on delete cascade,
  user_id     uuid not null references public.profiles(user_id) on delete cascade,
  username    text not null,
  created_at  timestamptz not null default now(),
  unique (giveaway_id, user_id)
);
create index giveaway_entries_giveaway_idx on public.giveaway_entries(giveaway_id);

-- custom_leaderboard: admin-edited Lockly add-ons
create table public.custom_leaderboard (
  id           uuid primary key default gen_random_uuid(),
  display_name text not null,
  wagered      numeric not null default 0,
  bets         int not null default 0,
  note         text,
  board        text not null default 'monthly' check (board in ('daily','weekly','monthly')),
  created_at   timestamptz not null default now()
);
create index custom_leaderboard_board_idx on public.custom_leaderboard(board);

-- live_status: single-row widget state
create table public.live_status (
  id         boolean primary key default true check (id = true),
  is_live    boolean not null default false,
  platform   text not null default 'kick',
  title      text,
  url        text default 'https://kick.com/greekgodberry',
  updated_at timestamptz not null default now()
);
insert into public.live_status (is_live) values (false) on conflict (id) do nothing;

-- app_admins: Discord-ID allowlist (the 3 admins). Replaces OWNER_EMAIL + ADMIN_DISCORD_IDS.
create table public.app_admins (
  discord_id text primary key,
  added_at   timestamptz not null default now()
);

-- =====================================================================
-- ADMIN ALLOWLIST SEED
-- =====================================================================
-- The 3 admin Discord IDs, with the leading-zero typo fixed in id #1.
-- id #1 was 040509012649181184 (invalid: Discord IDs never start with 0);
-- the correct ID is 940509012649181184 (matches stormy, used in the live chat-award test).
insert into public.app_admins (discord_id) values
  ('940509012649181184'),
  ('912757334199990942'),
  ('607951813789974578')
on conflict (discord_id) do nothing;

-- =====================================================================
-- HELPER: is_admin (server-side, claims trust only what we write)
-- =====================================================================
-- Reads app_metadata.role from the JWT. We set that claim server-side only,
-- in the assign-admin-role Edge Function. Anonymous client cannot assert it.
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin',
    false
  );
$$;

-- =====================================================================
-- RPC: award_points
-- Single transaction: cooldown gate + balance update + ledger insert.
-- All atomic. Idempotency-key uniqueness prevents duplicate chat/watch awards.
-- =====================================================================
create or replace function public.award_points(
  p_user_id         uuid,
  p_delta           int,
  p_reason          text,
  p_ref             text default null,
  p_idempotency_key text default null,
  p_cooldown_sec    int default 0
) returns table(awarded boolean, balance bigint, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_balance      bigint;
  v_last_ts      bigint;
  v_now          bigint := extract(epoch from now())::bigint;
  v_existing_id  bigint;
begin
  -- Cooldown gate (chat-award style). Skip if a recent ledger row exists.
  if p_cooldown_sec > 0 then
    select max(ts) into v_last_ts
      from public.ledger
     where user_id = p_user_id
       and reason  = p_reason
       and ts >= v_now - p_cooldown_sec;
    if v_last_ts is not null then
      return query select false, v_balance, 'cooldown'::text;
      return;
    end if;
  end if;

  -- Idempotency: if a ledger row with this key already exists, return its balance
  -- and the caller's caller can treat as duplicate (idempotent success).
  if p_idempotency_key is not null then
    select balance_after into v_balance
      from public.ledger
     where idempotency_key = p_idempotency_key;
    if v_balance is not null then
      return query select false, v_balance, 'duplicate'::text;
      return;
    end if;
  end if;

  -- Negative deltas require sufficient balance. Atomic check + update.
  if p_delta < 0 then
    update public.profiles
       set points_balance = points_balance + p_delta,
           updated_at     = now()
     where user_id = p_user_id
       and points_balance >= abs(p_delta)
    returning points_balance into v_balance;
    if v_balance is null then
      return query select false, 0::bigint, 'insufficient'::text;
      return;
    end if;
  else
    update public.profiles
       set points_balance = points_balance + p_delta,
           updated_at     = now()
     where user_id = p_user_id
    returning points_balance into v_balance;
  end if;

  v_now := extract(epoch from now())::bigint;

  -- Append-only ledger. ON CONFLICT (idempotency_key) DO NOTHING protects against
  -- a race where two callers both passed the cooldown check simultaneously.
  insert into public.ledger (user_id, delta, balance_after, reason, ref, idempotency_key, ts)
  values (p_user_id, p_delta, v_balance, p_reason, p_ref, p_idempotency_key, v_now)
  on conflict (idempotency_key) do nothing
  returning id into v_existing_id;

  if v_existing_id is null then
    -- Duplicate raced; the row from the winner is the one that exists. Re-read balance.
    select balance_after into v_balance
      from public.ledger
     where idempotency_key = p_idempotency_key;
    return query select false, v_balance, 'duplicate'::text;
    return;
  end if;

  return query select true, v_balance, 'awarded'::text;
end;
$$;

-- =====================================================================
-- RPC: watch_daily_count
-- Helper for the watch-points daily-cap check. Read-only.
-- =====================================================================
create or replace function public.watch_daily_count(p_user_id uuid)
returns int
language sql
stable
security definer
set search_path = public
as $$
  select count(*)::int
    from public.ledger
   where user_id = p_user_id
     and reason  = 'watch_time'
     and ts >= extract(epoch from date_trunc('day', now()))::bigint;
$$;

-- =====================================================================
-- RLS (deny-by-default)
-- =====================================================================
alter table public.profiles         enable row level security;
alter table public.ledger           enable row level security;
alter table public.rewards          enable row level security;
alter table public.stream_games     enable row level security;
alter table public.game_entries     enable row level security;
alter table public.giveaways        enable row level security;
alter table public.giveaway_entries enable row level security;
alter table public.custom_leaderboard enable row level security;
alter table public.live_status      enable row level security;
alter table public.app_admins       enable row level security;

-- profiles: users read their own row, update their own avatar/username; admins read all.
create policy profiles_self_select on public.profiles
  for select using (auth.uid() = user_id or public.is_admin());
create policy profiles_self_update on public.profiles
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ledger: users read their own; admins read all. No client writes.
create policy ledger_self_select on public.ledger
  for select using (
    exists (select 1 from public.profiles p where p.user_id = ledger.user_id and p.user_id = auth.uid())
    or public.is_admin()
  );

-- rewards, stream_games, giveaways, custom_leaderboard, live_status: public read.
create policy rewards_public_read on public.rewards for select using (true);
create policy stream_games_public_read on public.stream_games for select using (true);
create policy giveaways_public_read on public.giveaways for select using (true);
create policy custom_leaderboard_public_read on public.custom_leaderboard for select using (true);
create policy live_status_public_read on public.live_status for select using (true);

-- game_entries: user reads own + public game join lists; user inserts own.
create policy game_entries_public_read on public.game_entries for select using (true);
create policy game_entries_self_insert on public.game_entries
  for insert with check (auth.uid() = user_id);

-- giveaway_entries: same shape.
create policy giveaway_entries_public_read on public.giveaway_entries for select using (true);
create policy giveaway_entries_self_insert on public.giveaway_entries
  for insert with check (auth.uid() = user_id);

-- app_admins: readable by anyone authenticated (Edge Function enforces the write side).
create policy app_admins_read on public.app_admins for select using (auth.role() = 'authenticated');

-- No client INSERT/UPDATE/DELETE on ledger, rewards, stream_games, giveaways, custom_leaderboard,
-- live_status, app_admins. All writes go through RPC (award_points) or the service_role key
-- (Edge Functions for admin mutations, which can be added in a follow-up migration).

-- =====================================================================
-- AUTO-PROFILE TRIGGER: create public.profiles row on auth.users signup.
-- =====================================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_discord_id text;
  v_username   text;
  v_avatar     text;
  v_email      text;
  v_is_admin   boolean := false;
begin
  -- Supabase Auth stores provider info in raw_user_meta_data.
  -- For Discord provider, the sub claim + raw_user_meta_data has provider_id + identity_data.
  v_discord_id := coalesce(
    new.raw_user_meta_data ->> 'provider_id',
    new.raw_user_meta_data ->> 'sub',
    new.id::text
  );
  v_username   := coalesce(new.raw_user_meta_data ->> 'full_name',
                           new.raw_user_meta_data ->> 'name',
                           new.raw_user_meta_data ->> 'user_name',
                           'user_' || substr(new.id::text, 1, 8));
  v_avatar     := new.raw_user_meta_data ->> 'avatar_url';
  v_email      := new.email;

  -- Server-side admin check against the allowlist (not from any client claim).
  select exists(select 1 from public.app_admins where discord_id = v_discord_id)
    into v_is_admin;

  insert into public.profiles (user_id, discord_id, username, email, avatar_url, role)
  values (new.id, v_discord_id, v_username, v_email, v_avatar,
          case when v_is_admin then 'admin' else 'viewer' end)
  on conflict (user_id) do nothing;

  if v_is_admin then
    -- write app_metadata.role via the service role (Edge Function also writes it for refresh);
    -- from the trigger we cannot update auth.users directly without service_role, so the
    -- assign-admin-role Edge Function is the source of truth for app_metadata.role. This
    -- trigger writes profiles.role only.
    null;
  end if;

  return new;
end;
$$;

-- Trigger on auth.users.
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
