// chat-award-receiver
// The greek-bingo chat listener POSTs here when a user earns a chat point.
// We translate { discord_id, source, event_id, platform_username } into a Supabase
// RPC call: public.award_points(...). This keeps the cooldown/dedup atomic in Postgres.
//
// Auth: a shared secret header matches what the previous greek-web /internal/points/chat-award
// used. The greek-bingo backend is the only caller, so a simple shared secret is fine and
// preserves the existing INTERNAL_POINTS_SECRET rotation flow.
//
// Deploy: supabase functions deploy chat-award-receiver --no-verify-jwt
// Set CHAT_AWARD_SECRET in the Edge Function env to the same value greek-bingo uses.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface AwardBody {
  discord_id: string;
  source: "kick" | "twitch";
  platform_username: string;
  event_id: string;
}

const COOLDOWN_SECONDS = 180;

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const expected = Deno.env.get("CHAT_AWARD_SECRET");
  if (!expected) {
    return new Response("Server misconfigured", { status: 500 });
  }
  const provided = req.headers.get("x-internal-secret") ?? "";
  if (provided !== expected) {
    return new Response("Forbidden", { status: 401 });
  }

  let body: AwardBody;
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (!body?.discord_id || !body?.source || !body?.event_id) {
    return new Response("Missing fields", { status: 400 });
  }
  if (body.source !== "kick" && body.source !== "twitch") {
    return new Response("Invalid source", { status: 422 });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRole) {
    return new Response("Server misconfigured", { status: 500 });
  }
  const supabase = createClient(supabaseUrl, serviceRole, { auth: { persistSession: false } });

  // Resolve the profiles.user_id from the Discord ID. If the user has not signed in
  // via the main site yet, we cannot create a profile from a chat award alone
  // (Discord OAuth consent is how accounts are born).
  const { data: profile, error: pErr } = await supabase
    .from("profiles")
    .select("user_id")
    .eq("discord_id", body.discord_id)
    .maybeSingle();

  if (pErr) {
    return new Response(`Profile lookup failed: ${pErr.message}`, { status: 500 });
  }
  if (!profile) {
    return jsonResponse({ awarded: false, reason: "no_account" });
  }

  const { data, error } = await supabase.rpc("award_points", {
    p_user_id: profile.user_id,
    p_delta: 1,
    p_reason: `chat_${body.source}`,
    p_ref: `platform:${body.platform_username}`,
    p_idempotency_key: `chat_${body.source}_${body.event_id}`,
    p_cooldown_sec: COOLDOWN_SECONDS,
  });

  if (error) {
    return new Response(`RPC failed: ${error.message}`, { status: 500 });
  }

  // award_points returns a setof row: { awarded, balance, reason }.
  const row = Array.isArray(data) ? data[0] : data;
  return jsonResponse({
    awarded: Boolean(row?.awarded),
    balance: row?.balance ?? null,
    reason: row?.reason ?? null,
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
