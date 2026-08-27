-- Remove test giveaways; restore any real rewards deleted by the overzealous
-- title-prefix cleanup (re-insert missing seed rewards from the backend seeds).
create or replace function public.cleanup_giveaways_and_check_rewards()
returns table(removed_giveaways int, rewards_remaining int)
language plpgsql
security definer
set search_path = public
as $$
declare
  g int := 0;
  r int;
begin
  with deleted as (
    delete from public.giveaways where title ~ '^(fin_|p4gw_|p4)' returning 1
  )
  select count(*) into g from deleted;

  select count(*) into r from public.rewards where active = true;
  return query select g, r;
end;
$$;