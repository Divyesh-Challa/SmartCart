import { useState, type FormEvent } from "react";
import { api, type CompareResult } from "../lib/api";
import { formatFreshness, formatPrice } from "../lib/format";
import { loadLocation } from "../lib/storage";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, Spinner } from "../components/ui";

export default function ComparePage() {
  const location = loadLocation();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompareResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: query.trim() });
      if (location) params.set("postal_code", location.postalCode);
      const res = await api<{ data: CompareResult[] }>(`/api/v1/search/compare?${params}`);
      setResults(res.data.filter((r) => r.stores.length > 0));
    } catch (err) {
      setError((err as Error).message || t.errors.generic);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageTitle>{t.compare.title}</PageTitle>
      {!location && <Notice>{t.plan.needLocation}</Notice>}
      <form onSubmit={search} className="flex gap-2" role="search">
        <label htmlFor="compare-q" className="sr-only">{t.compare.placeholder}</label>
        <input id="compare-q" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.compare.placeholder}
          className="min-h-11 flex-1 rounded-xl border border-slate-300 px-3 dark:border-slate-700 dark:bg-slate-900" />
        <Button type="submit">{t.compare.search}</Button>
      </form>

      {loading && <Spinner label={t.plan.loading} />}
      {error && <Notice tone="error">{error}</Notice>}
      {results && results.length === 0 && <Notice>{t.compare.none}</Notice>}

      {results?.map((r) => (
        <Card key={r.product_id}>
          <h2 className="font-bold">{r.name}</h2>
          <p className="mb-2 text-xs text-slate-500">{r.standard_package}</p>
          <ul className="divide-y divide-slate-200 dark:divide-slate-800">
            {r.stores.map((st) => (
              <li key={st.store_id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="font-medium">
                    {st.store_name}
                    {st.is_lowest && <span className="ml-2 rounded-full bg-brand-50 px-2 py-0.5 text-xs font-semibold text-brand-800">{t.compare.lowest}</span>}
                  </p>
                  <p className="text-xs text-slate-500">
                    {st.distance_km != null && `${st.distance_km} km · `}
                    {st.flyer_deal
                      ? `${t.compare.flyer}${st.flyer_deal.discount_text ? `: ${st.flyer_deal.discount_text}` : ""}`
                      : st.reported_at
                        ? `${t.compare.reportedAt(st.reported_at)} · ${formatFreshness(st.last_observed_at)}`
                        : `${t.compare.reports(st.observation_count)} · ${formatFreshness(st.last_observed_at)}`}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-bold">{formatPrice(st.price)}</p>
                  <p className="text-xs text-slate-500">{st.unit_price_display}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </>
  );
}
