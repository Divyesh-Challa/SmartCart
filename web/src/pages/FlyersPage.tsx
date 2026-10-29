import { useEffect, useState } from "react";
import { api, type Flyer, type FlyerDeal } from "../lib/api";
import { formatPrice } from "../lib/format";
import { t } from "../i18n/en";
import { Card, Notice, PageTitle, Spinner } from "../components/ui";

function FlyerCard({ flyer }: { flyer: Flyer }) {
  const [deals, setDeals] = useState<FlyerDeal[] | null>(null);
  const [open, setOpen] = useState(false);

  async function toggle() {
    setOpen((o) => !o);
    if (!deals) {
      const res = await api<{ deals: FlyerDeal[] }>(`/api/flyers/${flyer.id}/deals`).catch(() => ({ deals: [] }));
      setDeals(res.deals);
    }
  }

  return (
    <Card>
      <button type="button" onClick={toggle} aria-expanded={open} className="flex w-full items-start justify-between text-left">
        <span>
          <span className="block font-bold">{flyer.banner}</span>
          <span className="block text-sm text-slate-600 dark:text-slate-400">{flyer.title}</span>
          <span className="block text-xs text-slate-500">{t.flyers.validUntil(flyer.valid_to)} · {flyer.deals_count} deals</span>
        </span>
        <span aria-hidden className="text-xl">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <ul className="mt-3 divide-y divide-slate-200 dark:divide-slate-800">
          {deals === null && <li><Spinner label={t.plan.loading} /></li>}
          {deals?.map((d) => (
            <li key={d.id} className="flex justify-between gap-3 py-2 text-sm">
              <span>{d.name}<span className="block text-xs text-slate-500">{d.discount_text}</span></span>
              <span className="font-bold">{formatPrice(d.price)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function FlyersPage() {
  const [flyers, setFlyers] = useState<Flyer[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api<{ flyers: Flyer[] }>("/api/flyers").then((r) => setFlyers(r.flyers)).catch(() => setError(true));
  }, []);

  return (
    <>
      <PageTitle>{t.flyers.title}</PageTitle>
      {error && <Notice tone="error">{t.errors.generic}</Notice>}
      {!flyers && !error && <Spinner label={t.plan.loading} />}
      {flyers && flyers.length === 0 && <Notice>{t.flyers.none}</Notice>}
      {flyers?.map((f) => <FlyerCard key={f.id} flyer={f} />)}
    </>
  );
}
