import { supabase } from "./supabase";

const BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

async function authHeader(): Promise<Record<string, string>> {
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(await authHeader()), ...(init.headers as Record<string, string>) };
  if (init.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? `Request failed (${res.status})`;
    throw new ApiError(res.status, message, body);
  }
  return body as T;
}

export const postJson = <T,>(path: string, data: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(data) });

// --- Response types (subset of fields the app uses) ---

export interface CoverageStats {
  total_stores_tracked: number;
  stores_with_prices: number;
  price_observations_30d: number;
  attribution: string;
}

export interface GeocodeResult {
  status: string;
  postal_code?: string;
  neighborhood?: string;
  lat?: number;
  lon?: number;
}

export interface Store {
  id: number;
  name: string;
  banner: string;
  address: string;
  city: string;
  distance_km?: number;
}

export interface PlanItem {
  item_name: string;
  requested: string;
  packages: number;
  total_cost: number;
  store_name: string;
  on_sale?: boolean;
  sale_ends?: string | null;
}

export interface PlanStore {
  store_name: string;
  chain: string;
  address: string;
  store_subtotal: number;
  items: PlanItem[];
  directions_url: string;
}

export interface Plan {
  grocery_cost: number;
  gas_cost: number;
  all_in_cost: number;
  total_distance_km: number;
  drive_time_minutes: number;
  stores: PlanStore[];
  full_route_directions_url: string;
}

export interface OptimizeResponse {
  plans: Record<string, Plan | null>;
  unmatched_items: { query: string }[];
  notice?: { code: string; message: string };
}

export interface CompareStore {
  store_id: number;
  store_name: string;
  banner: string;
  distance_km: number | null;
  price: number;
  unit_price_display: string;
  is_lowest: boolean;
  is_on_sale: boolean;
  observation_count: number;
  last_observed_at: string | null;
  flyer_deal: { discount_text: string | null; valid_until: string | null } | null;
}

export interface CompareResult {
  product_id: number;
  name: string;
  standard_package: string;
  stores: CompareStore[];
}

export interface Product {
  id: number;
  name: string;
  category: string;
  package_quantity: number;
  package_unit: string;
}

export interface BarcodeResult {
  found: boolean;
  barcode: string;
  name?: string | null;
  brand?: string | null;
  package_size?: string | null;
  image_url?: string | null;
  has_prices?: boolean;
  nutrition?: Record<string, number | string | null>;
  store_prices?: { store_id: number; store_name: string; banner: string; price: number; observation_count: number; last_observed_at: string | null; is_lowest: boolean }[];
  attribution?: string | null;
  message?: string;
}

export interface Flyer {
  id: number;
  banner: string;
  title: string;
  valid_to: string;
  deals_count: number;
}

export interface FlyerDeal {
  id: number;
  name: string;
  price: number;
  discount_text: string;
}

export interface Profile {
  id: string;
  email: string | null;
  display_name: string | null;
  marketing_opt_in: boolean;
  price_reports: number;
  plan: string;
  is_admin: boolean;
  has_full_access: boolean;
}

export interface PendingObservation {
  id: number;
  store_name: string;
  product_name: string | null;
  raw_item_name: string | null;
  upc: string | null;
  price: number;
  observed_at: string;
  current_median: number | null;
  current_count: number | null;
}
