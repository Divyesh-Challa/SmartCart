import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, postJson, type Flyer, type PendingObservation, type Profile } from "../lib/api";
import { useAuth } from "../lib/auth";
import { formatFreshness, formatPrice } from "../lib/format";
import { t } from "../i18n/en";
import { Button, Card, Notice, PageTitle, TextInput } from "../components/ui";

const today = () => new Date().toISOString().slice(0, 10);
const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10);

export interface ParsedDeal { title: string; category: string; sale_price: number; original_price?: number }

/** Parses "item | category | sale | regular" lines; returns the 1-based line number of the first bad line. */
export function parseDeals(text: string): { deals: ParsedDeal[]; badLine: number | null } {
  const deals: ParsedDeal[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    const [title, category, sale, regular] = line.split("|").map((p) => p.trim());
    const salePrice = Number(sale);
    if (!title || !category || !(salePrice > 0)) return { deals, badLine: i + 1 };
    const regularPrice = Number(regular);
    deals.push({ title, category, sale_price: salePrice, ...(regularPrice > 0 ? { original_price: regularPrice } : {}) });
  }
  return { deals, badLine: null };
}

function ReviewQueue() {
  const [items, setItems] = useState<PendingObservation[] | null>(null);
  const load = useCallback(() => {
    api<{ observations: PendingObservation[] }>("/api/admin/observations?status=pending").then((r) => setItems(r.observations));
  }, []);
  useEffect(load, [load]);

  async function decide(id: number, status: "accepted" | "rejected") {
    await postJson(`/api/admin/observations/${id}`, { status });
    setItems((prev) => prev?.filter((o) => o.id !== id) ?? null);
  }

  return (
    <Card>
      <h2 className="mb-2 font-bold">{t.admin.reviewTitle}</h2>
      {items?.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">{t.admin.reviewEmpty}</p>}
      <ul className="divide-y divide-slate-200 dark:divide-slate-800">
        {items?.map((o) => (
          <li key={o.id} className="space-y-2 py-3">
            <div className="flex justify-between gap-2">
              <div>
                <p className="font-medium">{o.product_name ?? o.raw_item_name ?? o.upc}</p>
                <p className="text-xs text-slate-500">{o.store_name} · {formatFreshness(o.observed_at)}</p>
                <p className="text-xs text-slate-500">
                  {o.current_median != null ? t.admin.current(formatPrice(o.current_median), o.current_count ?? 0) : t.admin.noCurrent}
                </p>
              </div>
              <p className="text-lg font-bold">{formatPrice(o.price)}</p>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => decide(o.id, "accepted")}>{t.admin.approve}</Button>
              <Button variant="secondary" onClick={() => decide(o.id, "rejected")}>{t.admin.reject}</Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FlyerManager() {
  const [banner, setBanner] = useState("");
  const [title, setTitle] = useState("");
  const [validFrom, setValidFrom] = useState(today);
  const [validTo, setValidTo] = useState(() => inDays(6));
  const [dealsText, setDealsText] = useState("");
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [flyers, setFlyers] = useState<Flyer[]>([]);

  const load = useCallback(() => {
    api<{ flyers: Flyer[] }>("/api/flyers").then((r) => setFlyers(r.flyers)).catch(() => setFlyers([]));
  }, []);
  useEffect(load, [load]);

  async function save(e: FormEvent) {
    e.preventDefault();
    const { deals, badLine } = parseDeals(dealsText);
    if (badLine) return setMessage({ tone: "error", text: t.admin.badLine(badLine) });
    try {
      await postJson("/api/admin/flyers", { banner, title, valid_from: validFrom, valid_to: validTo, deals });
      setMessage({ tone: "success", text: t.admin.flyerSaved(deals.length) });
      setDealsText("");
      load();
    } catch (err) {
      setMessage({ tone: "error", text: (err as Error).message });
    }
  }

  async function remove(id: number) {
    await api(`/api/admin/flyers/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <>
      <Card>
        <h2 className="mb-3 font-bold">{t.admin.flyerTitle}</h2>
        <form onSubmit={save} className="space-y-3">
          <TextInput id="banner" label={t.admin.banner} required value={banner} onChange={(e) => setBanner(e.target.value)} placeholder="No Frills" />
          <TextInput id="flyer-title" label={t.admin.flyerName} required value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="grid grid-cols-2 gap-3">
            <TextInput id="valid-from" type="date" label={t.admin.validFrom} required value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
            <TextInput id="valid-to" type="date" label={t.admin.validTo} required value={validTo} onChange={(e) => setValidTo(e.target.value)} />
          </div>
          <label htmlFor="deals" className="block">
            <span className="mb-1 block text-sm font-medium">{t.admin.dealsLabel}</span>
            <textarea id="deals" rows={6} value={dealsText} onChange={(e) => setDealsText(e.target.value)} placeholder={t.admin.dealsPlaceholder}
              className="w-full rounded-xl border border-slate-300 p-3 font-mono text-sm dark:border-slate-700 dark:bg-slate-900" />
          </label>
          <Button type="submit" className="w-full">{t.admin.saveFlyer}</Button>
        </form>
        {message && <div className="mt-3"><Notice tone={message.tone}>{message.text}</Notice></div>}
      </Card>
      <Card>
        <h2 className="mb-2 font-bold">{t.admin.onFile}</h2>
        {flyers.length === 0 && <p className="text-sm text-slate-600 dark:text-slate-400">{t.flyers.none}</p>}
        <ul className="divide-y divide-slate-200 dark:divide-slate-800">
          {flyers.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2 py-2">
              <span>{f.banner}: {f.title}<span className="block text-xs text-slate-500">{t.flyers.validUntil(f.valid_to)} · {f.deals_count} deals</span></span>
              <Button variant="secondary" onClick={() => remove(f.id)}>{t.admin.remove}</Button>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

export default function AdminPage() {
  const { session } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!session) return setChecked(true);
    api<Profile>("/api/me").then(setProfile).catch(() => setProfile(null)).finally(() => setChecked(true));
  }, [session]);

  if (!checked) return null;
  if (!profile?.is_admin) return <><PageTitle>{t.admin.title}</PageTitle><Notice>{t.admin.notAdmin}</Notice></>;

  return (
    <>
      <PageTitle>{t.admin.title}</PageTitle>
      <ReviewQueue />
      <FlyerManager />
    </>
  );
}
