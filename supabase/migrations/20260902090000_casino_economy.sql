-- Casino economy primitives for the Samurai Coin unification (GreekBot ⇄ website).
--
-- The bot's wallet operations are backed by the SAME canonical store the website
-- uses: public.profiles.points_balance + public.ledger (see award_points).
--
-- award_points (existing) already provides atomic, ledger-audited, idempotent
-- debit/credit — the bot uses it directly for bets, payouts, daily claims and
-- starter grants via deterministic idempotency keys.
--
-- This migration adds only what award_points cannot do alone:
--   1. casino_jackpot      — site-wide progressive jackpot pot (2% casino rake)
--   2. jackpot_contribute  — atomic rake contribution, returns the new pot
--   3. transfer_points     — atomic two-leg tip (debit-with-guard + credit in
--                            one transaction; two award_points calls could
--                            burn coins if the process died between them)

-- ------------------------------------------------------------------
-- 1. Jackpot pot (single row, enforced)
-- ------------------------------------------------------------------
create table if not exists public.casino_jackpot (
  id smallint primary key default 1 check (id = 1),
  amount bigint not null default 0,
  updated_at timestamptz not null default now()
);

insert into public.casino_jackpot (id, amount) values (1, 0)
on conflict (id) do nothing;

-- ------------------------------------------------------------------
-- 2. Rake contribution (atomic)
-- ------------------------------------------------------------------
create or replace function public.jackpot_contribute(p_amount bigint)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
  v_new bigint;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'invalid_amount';
  end if;
  update public.casino_jackpot
     set amount = amount + p_amount, updated_at = now()
   where id = 1
   returning amount into v_new;
  return v_new;
end;
$$;

-- ------------------------------------------------------------------
-- 3. Atomic tip (two legs, one transaction, idempotent on the out-row)
-- ------------------------------------------------------------------
create or replace function public.transfer_points(
  p_from uuid,
  p_to uuid,
  p_amount int,
  p_idempotency_key text
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_from_bal bigint;
  v_to_bal   bigint;
begin
  if p_amount is null or p_amount <= 0 then
    raise exception 'invalid_amount';
  end if;
  if p_from = p_to then
    raise exception 'self_transfer';
  end if;

  -- idempotency: the sender's out-row carries the caller-supplied key
  if exists (select 1 from public.ledger where idempotency_key = p_idempotency_key) then
    return jsonb_build_object(
      'reason', 'duplicate',
      'from_balance', (select points_balance from public.profiles where user_id = p_from)
    );
  end if;

  select points_balance into v_from_bal
    from public.profiles where user_id = p_from for update;
  if v_from_bal is null then
    raise exception 'no_profile_from';
  end if;
  if v_from_bal < p_amount then
    raise exception 'insufficient';
  end if;

  select points_balance into v_to_bal
    from public.profiles where user_id = p_to for update;
  if v_to_bal is null then
    raise exception 'no_profile_to';
  end if;

  update public.profiles
     set points_balance = points_balance - p_amount, updated_at = now()
   where user_id = p_from;
  insert into public.ledger (user_id, delta, balance_after, reason, idempotency_key, ref)
  values (p_from, -p_amount, v_from_bal - p_amount, 'tip_out', p_idempotency_key, p_to::text);

  update public.profiles
     set points_balance = points_balance + p_amount, updated_at = now()
   where user_id = p_to;
  insert into public.ledger (user_id, delta, balance_after, reason, ref)
  values (p_to, p_amount, v_to_bal + p_amount, 'tip_in', p_from::text);

  return jsonb_build_object(
    'reason', 'ok',
    'from_balance', v_from_bal - p_amount,
    'to_balance', v_to_bal + p_amount
  );
end;
$$;
