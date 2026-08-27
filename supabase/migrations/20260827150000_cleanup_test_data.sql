-- One-shot cleanup of test leftovers from the Phase 4 RPC test suite runs.
create or replace function public.cleanup_phase4_test_data()
returns table(removed_games int, removed_rewards int, removed_profiles int)
language plpgsql
security definer
set search_path = public
as $$
declare
  g int := 0;
  r int := 0;
  p int := 0;
begin
  -- test games (any title not in the real seed set)
  with deleted as (
    delete from public.stream_games
     where title not in ('Bonus Hunt','Tournament','Chat vs Streamer','Climb the Ladder','Bonus Bingo')
    returning 1
  )
  select count(*) into g from deleted;

  -- test rewards
  with deleted as (
    delete from public.rewards
     where title ~ '^(p4|fin|tr|dbg|probe)'
    returning 1
  )
  select count(*) into r from deleted;

  -- test profiles (and their ledger rows via explicit delete first)
  with targets as (
    select user_id from public.profiles
     where discord_id ~ '^(p4|fin|tr|dbg|bal)'
  ), del_ledger as (
    delete from public.ledger l using targets t where l.user_id = t.user_id returning 1
  )
  delete from public.profiles pr using targets t where pr.user_id = t.user_id;
  get diagnostics p = row_count;

  return query select g, r, p;
end;
$$;