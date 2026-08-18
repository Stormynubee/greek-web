export function cleanAuthFeedbackQuery(search) {
  const params = new URLSearchParams(search);
  const authTicket = params.get("auth_ticket");

  params.delete("auth");
  params.delete("reason");

  return {
    authTicket,
    search: params.toString() ? `?${params.toString()}` : "",
  };
}
