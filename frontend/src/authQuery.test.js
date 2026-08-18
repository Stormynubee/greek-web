import { cleanAuthFeedbackQuery } from "./authQuery";

test("preserves auth_ticket while clearing the feedback flags", () => {
  expect(cleanAuthFeedbackQuery("?auth=success&auth_ticket=handoff-123")).toEqual({
    authTicket: "handoff-123",
    search: "?auth_ticket=handoff-123",
  });
});
