-- Fix ambiguity in award_points: the RETURNS TABLE(out) output columns (user_id
-- not present, but reason/ts collide with ledger columns) make bare column refs
-- ambiguous. Fully qualify all public.ledger.* references.

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
  v_profile_exists boolean;
begin
  -- Guard: target profile (user) must exist.
  select exists(select 1 from public.profiles where user_id = p_user_id)
    into v_profile_exists;
  if not v_profile_exists then
    return query select false, 0::bigint, 'no_profile'::text;
    return;
  end if;

  -- Cooldown gate (chat-award). Fully-qualified columns to avoid ambiguity.
  if p_cooldown_sec > 0 then
    select max(public.ledger.ts) into v_last_ts
      from public.ledger
     where public.ledger.user_id = p_user_id
       and public.ledger.reason  = p_reason
       and public.ledger.ts >= v_now - p_cooldown_sec;
    if v_last_ts is not null then
      return query select false, v_balance, 'cooldown'::text;
      return;
    end if;
  end if;

  -- Idempotency: duplicate key -> return existing balance_after, no new award.
  if p_idempotency_key is not null then
    select public.ledger.balance_after into v_balance
      from public.ledger
     where public.ledger.idempotency_key = p_idempotency_key;
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

  -- Append-only ledger. ON CONFLICT (idempotency_key) DO NOTHING guards races.
  insert into public.ledger (user_id, delta, balance_after, reason, ref, idempotency_key, ts)
  values (p_user_id, p_delta, v_balance, p_reason, p_ref, p_idempotency_key, v_now)
  on conflict (idempotency_key) do nothing
  returning id into v_existing_id;

  if v_existing_id is null then
    select public.ledger.balance_after into v_balance
      from public.ledger
     where public.ledger.idempotency_key = p_idempotency_key;
    return query select false, v_balance, 'duplicate'::text;
    return;
  end if;

  return query select true, v_balance, 'awarded'::text;
end;
$$;