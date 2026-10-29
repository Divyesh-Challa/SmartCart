import { useEffect, useState } from "react";
import { postJson, type OptimizeResponse, type Plan } from "../lib/api";
import { formatPrice } from "../lib/format";
import { loadList, loadLocation } from "../lib/storage";
import { t } from "../i18n/en";
import { Card, Notice, PageTitle, Spinner } from "../components/ui";

const PLAN_ORDER = ["plan_1_split", "plan_2_single", "plan_3_stock"];

function PlanCard({ planKey, plan }: { planKey: string; plan: Plan }) {
  return (
    <Card className="space-y-3">
      <div>
        <h2 className="text-lg font-bold">{t.plan.planNames[planKey]}</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">{t.plan.planHints[planKey]}</p>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-center">
        <div><dt className="text-xs text-slate-500">{t.plan.grocery}</dt><dd className="font-semibold">{formatPrice(plan.grocery_cost)}</dd></div>
        <div><dt className="text-xs text-slate-500">{t.plan.fuel}</dt><dd className="font-semibold">{formatPrice(plan.gas_cost)}</dd></div>
        <div><dt className="text-xs text-slate-500">{t.plan.total}</dt><dd className="text-lg font-bold text-brand-700 dark:text-brand-100">{formatPrice(plan.all_in_cost)}</dd></div>
      </dl>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        {t.plan.stops(plan.stores.length)} · {plan.total_distance_km} km · ~{plan.drive_time_minutes} min
      </p>
      <ul className="space-y-2">
        {plan.stores.map((st) => (
          <li key={st.store_name} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-semibold">{st.store_name}</p>
                {st.address && <p className="text-xs text-slate-500">{st.address}</p>}
              </div>
              <a href={st.directions_url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-brand-700 underline dark:text-brand-100">
                {t.plan.directions}
              </a>
            </div>
            <ul className="mt-2 space-y-1 text-sm">
              {st.items.map((it) => (
                <li key={it.requested} className="flex justify-between">
                  <span>
                    {it.packages} × {it.item_name}
                    {it.on_sale && (
                      <span className="ml-2 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900 dark:bg-amber-900/40 dark:text-amber-100">
                        {t.plan.onSale(it.sale_ends ?? "")}
                      </span>
                    )}
                  </span>
                  <span>{formatPrice(it.total_cost)}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export default function PlanPage() {
  const location = loadLocation();
  const items = loadList();
  const [result, setResult] = useState<OptimizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = !!location && items.length > 0;

  useEffect(() => {
    if (!ready) return;
    postJson<OptimizeResponse>("/api/optimize", {
      items: items.map((it) => ({ name: it.name, quantity: it.quantity })),
      postal_code: location!.postalCode,
    })
      .then(setResult)
      .catch((e: Error) => setError(e.message || t.errors.generic));
    // Run once per visit with the list as it was when the page opened.
  }, []);

  if (!location) return <><PageTitle>{t.plan.title}</PageTitle><Notice>{t.plan.needLocation}</Notice></>;
  if (!items.length) return <><PageTitle>{t.plan.title}</PageTitle><Notice>{t.plan.needItems}</Notice></>;

  const plans = PLAN_ORDER.map((k) => [k, result?.plans[k]] as const).filter((p): p is readonly [string, Plan] => !!p[1]);

  return (
    <>
      <PageTitle>{t.plan.title}</PageTitle>
      {!result && !error && <Spinner label={t.plan.loading} />}
      {error && <Notice tone="error">{error}</Notice>}
      {result && plans.length === 0 && (
        <Notice><strong>{t.plan.noData}.</strong> {result.notice?.message}</Notice>
      )}
      {result && result.unmatched_items.length > 0 && (
        <Notice>{t.plan.unmatched(result.unmatched_items.map((u) => u.query).join(", "))}</Notice>
      )}
      {plans.map(([key, plan]) => <PlanCard key={key} planKey={key} plan={plan} />)}
      {plans.length > 0 && <p className="text-xs text-slate-500">{t.plan.disclaimer}</p>}
    </>
  );
}
