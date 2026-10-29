import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, postJson, type CoverageStats, type GeocodeResult } from "../lib/api";
import { normalizePostalCode } from "../lib/format";
import { loadLocation, saveLocation, type SavedLocation } from "../lib/storage";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, TextInput } from "../components/ui";

export default function HomePage() {
  const [location, setLocation] = useState<SavedLocation | null>(loadLocation);
  const [postal, setPostal] = useState(location?.postalCode ?? "");
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<CoverageStats | null>(null);

  useEffect(() => {
    api<CoverageStats>("/api/coverage/stats").then(setStats).catch(() => setStats(null));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const pc = normalizePostalCode(postal);
    if (!pc) return setError(t.home.invalidPostal);
    try {
      const geo = await postJson<GeocodeResult>("/api/geocode", { query: pc });
      if (geo.status !== "ok") return setError(t.home.invalidPostal);
      const loc = { postalCode: geo.postal_code ?? pc, area: geo.neighborhood ?? "" };
      saveLocation(loc);
      setLocation(loc);
    } catch {
      setError(t.errors.generic);
    }
  }

  return (
    <>
      <div className="space-y-2 pt-2">
        <PageTitle>{t.home.title}</PageTitle>
        <p className="text-slate-600 dark:text-slate-400">{t.home.subtitle}</p>
        {stats && (
          <p className="text-sm font-medium text-brand-700 dark:text-brand-100">
            {t.home.stats(stats.total_stores_tracked, stats.stores_with_prices)}
          </p>
        )}
      </div>

      <Card>
        <form onSubmit={onSubmit} className="space-y-3" noValidate>
          <TextInput id="postal" label={t.home.postalLabel} placeholder={t.home.postalPlaceholder} value={postal}
            onChange={(e) => setPostal(e.target.value)} autoComplete="postal-code" inputMode="text" />
          <Button type="submit" className="w-full">{t.home.save}</Button>
        </form>
        <div className="mt-3 space-y-2">
          {error && <Notice tone="error">{error}</Notice>}
          {location && !error && <Notice tone="success">{t.home.locationSet(location.postalCode, location.area)}</Notice>}
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Link to="/scan" className="rounded-2xl border border-slate-200 p-4 font-semibold dark:border-slate-800">{"📷 "}{t.scan.title}</Link>
        <Link to="/flyers" className="rounded-2xl border border-slate-200 p-4 font-semibold dark:border-slate-800">{"🗞️ "}{t.flyers.title}</Link>
      </div>

      <Card>
        <h2 className="mb-2 font-semibold">{t.home.howItWorks}</h2>
        <ol className="list-decimal space-y-1 pl-5 text-slate-700 dark:text-slate-300">
          {t.home.steps.map((s) => <li key={s}>{s}</li>)}
        </ol>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
          {t.home.helpBuild} <Link to="/add-price" className="font-semibold text-brand-700 underline dark:text-brand-100">{t.nav.addPrice}</Link>
        </p>
      </Card>
    </>
  );
}
