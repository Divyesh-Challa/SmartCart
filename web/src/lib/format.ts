import { t } from "../i18n/en";

const currency = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" });

export function formatPrice(value: number | null | undefined): string {
  return value == null ? "—" : currency.format(value);
}

/** "today", "yesterday", "3 days ago" for an ISO timestamp, relative to `now`. */
export function formatFreshness(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return t.freshness.unknown;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return t.freshness.unknown;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(then)) / 86_400_000);
  if (days <= 0) return t.freshness.today;
  if (days === 1) return t.freshness.yesterday;
  return t.freshness.daysAgo(days);
}

const POSTAL_RE = /^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] ?\d[ABCEGHJ-NPRSTV-Z]\d$/i;

/** Normalizes a Canadian postal code to "A1A 1A1", or returns null if invalid. */
export function normalizePostalCode(raw: string): string | null {
  const compact = raw.replace(/\s+/g, "").toUpperCase();
  if (!POSTAL_RE.test(compact)) return null;
  return `${compact.slice(0, 3)} ${compact.slice(3)}`;
}
