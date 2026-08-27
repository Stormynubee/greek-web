-- Fix join_game: a duplicate join must NOT keep the entry-fee debit.
-- Pre-check before debiting; on a true race, re-raise so the whole
-- transaction (including the debit) rolls back.
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
  v_res     record;
  v_profile boolean;
  v_dup     boolean;
begin
  select exists(select 1 from public.profiles where user_id = p_user_id) into v_profile;
  if not v_profile then
    return query select false, 0::bigint, 'no_profile'::text; return;
  end if;

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

  -- Duplicate pre-check BEFORE any debit.
  select exists(
    select 1 from public.game_entries
     where game_id = p_game_id and user_id = p_user_id
  ) into v_dup;
  if v_dup then
    select points_balance into v_balance from public.profiles where user_id = p_user_id;
    return query select false, v_balance, 'already_joined'::text; return;
  end if;

  v_cost := v_game.entry_cost;

  if v_cost > 0 then
    select * into v_res from public.award_points(
      p_user_id, -v_cost, 'game_entry', p_game_id::text, p_idempotency_key, 0);
    if v_res.reason <> 'awarded' then
      return query select false, 0::bigint, v_res.reason::text; return;
    end if;
    v_balance := v_res.balance;
  else
    select points_balance into v_balance from public.profiles where user_id = p_user_id;
  end if;

  begin
    insert into public.game_entries (game_id, user_id, choice, stake)
    values (p_game_id, p_user_id, p_choice, v_cost);
  exception when unique_violation then
    -- Lost a race against a concurrent join: re-raise to roll back the debit.
    raise exception 'duplicate_game_entry';
  end;

  return query select true, v_balance, 'joined'::text;
end;
$$;