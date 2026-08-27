-- Fix ambiguous 'reason' in revoke_last_admin_grant (same as award_points fix):
-- qualify the ledger column against the OUT-table variable name.
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
    where public.ledger.user_id = p_user_id
      and public.ledger.reason  = 'admin_grant'
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
    v_target.ref,
    'revoke_' || coalesce(v_target.idempotency_key, v_target.id::text), 0);
  return query select v_res.awarded, v_res.balance, v_res.reason;
end;
$$;