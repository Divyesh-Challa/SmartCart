import { createClient, type SupabaseClient } from "@supabase/supabase-js";

declare global {
  interface Window {
    /** Set by /config.js, which the API serves from its environment. */
    __SMARTCART_CONFIG__?: { supabaseUrl?: string | null; supabaseAnonKey?: string | null };
  }
}

const runtime = typeof window !== "undefined" ? window.__SMARTCART_CONFIG__ : undefined;
const url = runtime?.supabaseUrl || (import.meta.env.VITE_SUPABASE_URL as string | undefined);
const anonKey = runtime?.supabaseAnonKey || (import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined);

/** Null until the Supabase project is configured; the app then runs without accounts. */
export const supabase: SupabaseClient | null = url && anonKey ? createClient(url, anonKey) : null;
