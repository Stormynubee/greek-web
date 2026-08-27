-- Phase 4: transactional RPCs for store redeem, game join, giveaway enter,
-- and admin revoke. All SECURITY DEFINER, single round trip, idempotency-guarded.

-- ------------------------------------------------------------------
-- redeem_reward: atomic stock check + balance debit + ledger row.
-- stock = -1 means unlimited.
-- ------------------------------------------------------------------
create or replace function public.redeem_reward(
  p_user_id         uuid,
  p_reward_id       uuid,
  p_idempotency_key text
) returns table(awarded boolean, balance bigint, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_reward      public.rewards%rowtype;
  v_balance     bigint;
  v_profile     boolean;
  v_existing    bigint;
begin
  select exists(select 1 from public.profiles where user_id = p_user_id) into v_profile;
  if not v_profile then
    return query select false, 0::bigint, 'no_profile'::text; return;
  end if;

  -- Idempotent replay returns the original outcome.
  if p_idempotency_key is not null then
    select l.balance_after into v_existing from public.ledger l
      where l.idempotency_key = p_idempotency_key;
    if v_existing is not null then
      return query select false, v_existing, 'duplicate'::text; return;
    end if;
  end if;

  select * into v_reward from public.rewards where id = p_reward_id for update;
  if not found or not v_reward.active then
    return query select false, 0::bigint, 'reward_unavailable'::text; return;
  end if;
  if v_reward.stock = 0 then
    return query select false, 0::bigint, 'out_of_stock'::text; return;
  end if;

  update public.rewards set stock = stock - 1
    where id = p_reward_id and stock > 0
    returning stock into v_reward.stock;
  if v_reward.stock is null then
    return query select false, 0::bigint, 'out_of_stock'::text; return;
  end if;

  update public.profiles
     set points_balance = points_balance - v_reward.cost, updated_at = now()
   where user_id = p_user_id and points_balance >= v_reward.cost
   returning points_balance into v_balance;
  if v_balance is null then
    -- refund the stock we just took
    update public.rewards set stock = stock + 1 where id = p_reward_id;
    return query select false, 0::bigint, 'insufficient'::text; return;
  end if;

  insert into public.ledger (user_id, delta, balance_after, reason, ref, idempotency_key, ts)
  values (p_user_id, -v_reward.cost, v_balance, 'store_redeem', p_reward_id::text, p_idempotency_key,
          extract(epoch from now())::bigint);

  return query select true, v_balance, 'redeemed'::text;
end;
$$;

-- ------------------------------------------------------------------
-- join_game: open check + choice validation + optional cost debit + entry.
-- ------------------------------------------------------------------
create or replace function public.join_game(
  p_game_id         uuid,
  p_user_id         uuid,
  p_choice          text,
  p_username        text,
  p_idempotency_key text
) returns table(ok boolean, balance bigint, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_game    public.stream_games%rowtype;
  v_balance bigint;
  v_cost    int;
begin
  select * into v_game from public.stream_games where id = p_game_id;
  if not found then
    return query select false, 0::bigint, 'not_found'::text; return;
  end if;
  if v_game.status <> 'open' then
    return query select false, 0::bigint, 'closed'::text; return;
  end if;
  if jsonb_array_length(v_game.options) > 0 and (p_choice is null or
     not exists (select 1 from jsonb_array_elements_text(v_game.options) o where o = p_choice)) then
    return query select false, 0::bigint, 'invalid_choice'::text; return;
  end if;

  v_cost := v_game.entry_cost;

  -- Cost debit (atomic, with idempotency) then entry insert.
  if v_cost > 0 then
    select awarded, balance, reason into v_balance, v_balance, reason
      from public.award_points(p_user_id, -v_cost, 'game_entry', p_game_id::text, p_idempotency_key, 0);
    if reason <> 'awarded' then
      return query select false, 0::bigint, reason; return;
    end if;
  else
    select points_balance into v_balance from public.profiles where user_id = p_user_id;
  end if;

  begin
    insert into public.game_entries (game_id, user_id, choice, stake)
    values (p_game_id, p_user_id, p_choice, v_cost);
  exception when unique_violation then
    return query select false, v_balance, 'already_joined'::text; return;
  end;

  return query select true, v_balance, 'joined'::text;
end;
$$;

-- ------------------------------------------------------------------
-- enter_giveaway: open check + unique entry + entry count.
-- ------------------------------------------------------------------
create or replace function public.enter_giveaway(
  p_giveaway_id uuid,
  p_user_id     uuid,
  p_username    text
) returns table(ok boolean, entries int, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_status text;
  v_count  int;
begin
  select status into v_status from public.giveaways where id = p_giveaway_id;
  if not found then
    return query select false, 0, 'not_found'::text; return;
  end if;
  if v_status <> 'open' then
    return query select false, 0, 'closed'::text; return;
  end if;

  begin
    insert into public.giveaway_entries (giveaway_id, user_id, username)
    values (p_giveaway_id, p_user_id, p_username);
  exception when unique_violation then
    return query select false, 0, 'already_entered'::text; return;
  end;

  select count(*)::int into v_count from public.giveaway_entries where giveaway_id = p_giveaway_id;
  return query select true, v_count, 'entered'::text;
end;
$$;

-- ------------------------------------------------------------------
-- revoke_last_admin_grant: find most recent admin_grant, reverse it.
-- ------------------------------------------------------------------
create or replace function public.revoke_last_admin_grant(
  p_user_id uuid
) returns table(awarded boolean, balance bigint, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_target  public.ledger%rowtype;
  v_res     record;
begin
  select * into v_target from public.ledger
    where user_id = p_user_id and reason = 'admin_grant'
    order by created_at desc, id desc limit 1;
  if not found then
    return query select false, 0::bigint, 'no_grant'::text; return;
  end if;
  if v_target.delta = 0 then
    return query select false, 0::bigint, 'no_op'::text; return;
  end if;

  select * into v_res from public.award_points(
    p_user_id, -v_target.delta, 'admin_revoke',
    v_target.idempotency_key,
    'revoke_' || coalesce(v_target.idempotency_key, v_target.id::text), 0);
  return query select v_res.awarded, v_res.balance, v_res.reason;
end;
$$;

-- ------------------------------------------------------------------
-- watch_daily_count exists from the init migration. Add the watch-beat
-- award as one RPC: cap check + bucketed idempotent award.
-- ------------------------------------------------------------------
create or replace function public.watch_beat(
  p_user_id uuid,
  p_bucket  bigint,
  p_daily_cap int
) returns table(awarded boolean, balance bigint, reason text)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_res     record;
  v_today   int;
  v_day_start bigint := extract(epoch from date_trunc('day', now()))::bigint;
begin
  select count(*)::int into v_today from public.ledger
    where user_id = p_user_id and reason = 'watch_time' and ts >= v_day_start;
  if v_today >= p_daily_cap then
    return query select false, 0::bigint, 'daily_cap'::text; return;
  end if;

  select * into v_res from public.award_points(
    p_user_id, 1, 'watch_time', 'stream_watch',
    'watch_' || p_user_id::text || '_' || p_bucket::text, 0);
  return query select v_res.awarded, v_res.balance, v_res.reason;
end;
$$;