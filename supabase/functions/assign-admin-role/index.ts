// assign-admin-role
// Supabase Auth hook: on Discord sign-in, check provider_id against public.app_admins.
// If admin, write app_metadata.role='admin' so the JWT carries an admin claim the RLS
// policies trust. Called as a Postgres Auth hook (custom_access_token_hook) OR directly
// from the frontend right after signInWithOAuth, passing the user's access token.
//
// This file is the Deno-style Edge Function. Deploy with:
//   supabase functions deploy assign-admin-role --no-verify-jwt
// Then enable it in the Supabase dashboard under Auth -> Hooks (Custom Access Token Hook)
// pointing at this function URL.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

interface HookPayload {
  user_id: string;
  claims: Record<string, unknown>;
}

// When used as a Custom Access Token Hook, Supabase POSTs { user_id, claims } and
// expects back { claims: { ...enriched } }. The service_role key is required to
// update auth.users.app_metadata.
export const config = { verify_jwt: false };

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceRole = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!supabaseUrl || !serviceRole) {
    return new Response("Missing server env", { status: 500 });
  }

  const supabase = createClient(supabaseUrl, serviceRole, {
    auth: { persistSession: false },
  });

  let payload: HookPayload;
  try {
    payload = await req.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }

  if (!payload?.user_id) {
    return new Response("Missing user_id", { status: 400 });
  }

  // Look up the profile's discord_id and check the admin allowlist.
  const { data: profile, error: pErr } = await supabase
    .from("profiles")
    .select("discord_id, role")
    .eq("user_id", payload.user_id)
    .single();

  if (pErr || !profile) {
    // No profile yet — return the original claims unchanged.
    return jsonResponse({ claims: payload.claims ?? {} });
  }

  const { data: adminRow } = await supabase
    .from("app_admins")
    .select("discord_id")
    .eq("discord_id", profile.discord_id)
    .maybeSingle();

  const isAdmin = Boolean(adminRow);
  const role = isAdmin ? "admin" : "viewer";

  // Ensure profiles.role mirrors the allowlist.
  if (profile.role !== role) {
    await supabase
      .from("profiles")
      .update({ role, updated_at: new Date().toISOString() })
      .eq("user_id", payload.user_id);
  }

  // Persist role into auth.users.app_metadata so every token issued from the DB
  // (including refreshes) carries it, not just tokens built from this response.
  try {
    const { data: cur } = await supabase.auth.admin.getUserById(payload.user_id);
    if (cur?.user && (cur.user.app_metadata?.role ?? null) !== role) {
      await supabase.auth.admin.updateUserById(payload.user_id, {
        app_metadata: { ...(cur.user.app_metadata ?? {}), role },
      });
    }
  } catch {
    // Non-fatal: claim enrichment below still applies to this token.
  }

  // Enrich the JWT claims. app_metadata is server-controlled and trusted by is_admin().
  const appMetadata = {
    ...(typeof payload.claims?.app_metadata === "object" && payload.claims.app_metadata !== null
      ? payload.claims.app_metadata
      : {}),
    role,
  };

  return jsonResponse({
    claims: {
      ...(payload.claims ?? {}),
      app_metadata: appMetadata,
    },
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
