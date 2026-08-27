import { createClient } from "@supabase/supabase-js";

const supabaseUrl = (process.env.REACT_APP_SUPABASE_URL || "").trim();
const supabaseAnonKey = (process.env.REACT_APP_SUPABASE_ANON_KEY || "").trim();

export const SUPABASE_CONFIGURED = Boolean(supabaseUrl && supabaseAnonKey);

export const supabase = SUPABASE_CONFIGURED
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;

/** The current Supabase access token, or null. Used as the shared Bearer token. */
export async function getSupabaseAccessToken() {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data?.session?.access_token ?? null;
}