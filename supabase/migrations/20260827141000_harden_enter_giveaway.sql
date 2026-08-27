-- Harden enter_giveaway with the same pre-check pattern (no cost today, but
-- a paid-entry future would hit the same duplicate-charge trap).
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
  v_dup    boolean;
begin
  select status into v_status from public.giveaways where id = p_giveaway_id;
  if not found then
    return query select false, 0, 'not_found'::text; return;
  end if;
  if v_status <> 'open' then
    return query select false, 0, 'closed'::text; return;
  end if;

  select exists(
    select 1 from public.giveaway_entries
     where giveaway_id = p_giveaway_id and user_id = p_user_id
  ) into v_dup;
  if v_dup then
    select count(*)::int into v_count from public.giveaway_entries where giveaway_id = p_giveaway_id;
    return query select false, v_count, 'already_entered'::text; return;
  end if;

  begin
    insert into public.giveaway_entries (giveaway_id, user_id, username)
    values (p_giveaway_id, p_user_id, p_username);
  exception when unique_violation then
    raise exception 'duplicate_giveaway_entry';
  end;

  select count(*)::int into v_count from public.giveaway_entries where giveaway_id = p_giveaway_id;
  return query select true, v_count, 'entered'::text;
end;
$$;