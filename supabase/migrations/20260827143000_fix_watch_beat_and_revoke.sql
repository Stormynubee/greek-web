-- Fix ambiguous 'reason' in watch_beat; also make revoke_last_admin_grant
-- skip already-reversed grants so a second revoke returns 'no_grant'.

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
    where public.ledger.user_id = p_user_id
      and public.ledger.reason  = 'watch_time'
      and public.ledger.ts >= v_day_start;
  if v_today >= p_daily_cap then
    return query select false, 0::bigint, 'daily_cap'::text; return;
  end if;

  select * into v_res from public.award_points(
    p_user_id, 1, 'watch_time', 'stream_watch',
    'watch_' || p_user_id::text || '_' || p_bucket::text, 0);
  return query select v_res.awarded, v_res.balance, v_res.reason;
end;
$$;

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
  -- Latest admin_grant that is not already reversed by an admin_revoke
  -- referencing it. Prevents double-revocation with clean semantics.
  select * into v_target from public.ledger
    where public.ledger.user_id = p_user_id
      and public.ledger.reason  = 'admin_grant'
      and not exists (
        select 1 from public.ledger r
         where r.reason = 'admin_revoke'
           and r.ref = coalesce(public.ledger.idempotency_key, public.ledger.id::text)
      )
    order by public.ledger.created_at desc, public.ledger.id desc
    limit 1;
  if not found then
    return query select false, 0::bigint, 'no_grant'::text; return;
  end if;
  if v_target.delta = 0 then
    return query select false, 0::bigint, 'no_op'::text; return;
  end if;

  select * into v_res from public.award_points(
    p_user_id, -v_target.delta, 'admin_revoke',
    coalesce(v_target.idempotency_key, v_target.id::text),
    'revoke_' || coalesce(v_target.idempotency_key, v_target.id::text), 0);
  return query select v_res.awarded, v_res.balance, v_res.reason;
end;
$$;