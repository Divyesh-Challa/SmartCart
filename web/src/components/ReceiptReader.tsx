import { useState, type ChangeEvent } from "react";
import { ApiError, postJson } from "../lib/api";
import { readReceipt } from "../lib/receipt";
import { t } from "../i18n/en";
import { Button, Card, Notice } from "./ui";

interface Row {
  key: number;
  name: string;
  price: string;
  include: boolean;
}

interface Summary {
  accepted: number;
  pending: number;
  unmatched: string[];
  failed: number;
}

/** Reads a receipt photo on the device and submits the confirmed lines as price reports. */
export default function ReceiptReader({ storeId, date }: { storeId: string; date: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sending, setSending] = useState(false);

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    setSummary(null);
    setRows([]);
    setProgress(0);
    try {
      const lines = await readReceipt(file, setProgress);
      if (!lines.length) setError(t.receipt.nothingFound);
      setRows(lines.map((l, i) => ({ key: i, name: l.name, price: l.price.toFixed(2), include: true })));
    } catch {
      setError(t.receipt.readFailed);
    } finally {
      setProgress(null);
    }
  }

  const update = (key: number, patch: Partial<Row>) => setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));

  async function submitAll() {
    setSending(true);
    const result: Summary = { accepted: 0, pending: 0, unmatched: [], failed: 0 };
    for (const row of rows.filter((r) => r.include && r.name.trim() && Number(rowPrice(r)) > 0)) {
      try {
        const res = await postJson<{ status: string }>("/api/prices/observations", {
          store_id: Number(storeId), price: Number(rowPrice(row)), item_name: row.name.trim(),
          observed_on: date, source: "receipt",
        });
        if (res.status === "accepted") result.accepted += 1;
        else result.pending += 1;
      } catch (err) {
        if (err instanceof ApiError && err.status === 422) result.unmatched.push(row.name.trim());
        else result.failed += 1;
      }
    }
    setSummary(result);
    setRows([]);
    setSending(false);
  }

  const ready = !!storeId && !!date;
  const selected = rows.filter((r) => r.include).length;

  return (
    <Card className="space-y-3">
      <h2 className="font-bold">{t.receipt.title}</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400">{t.receipt.intro}</p>
      {!ready && <Notice>{t.receipt.chooseStoreFirst}</Notice>}
      <label className={`flex min-h-11 w-full cursor-pointer items-center justify-center rounded-xl border border-brand-700 px-4 font-semibold text-brand-700 focus-within:ring-2 focus-within:ring-brand-700 dark:text-brand-100 ${ready && progress === null ? "" : "pointer-events-none opacity-50"}`}>
        {t.receipt.choose}
        <input type="file" accept="image/*" capture="environment" disabled={!ready || progress !== null} onChange={onFile} className="sr-only" />
      </label>
      {progress !== null && <p aria-live="polite" className="text-sm">{t.receipt.reading(Math.round(progress * 100))}</p>}
      {error && <Notice tone="error">{error}</Notice>}

      {rows.length > 0 && (
        <>
          <p className="text-sm">{t.receipt.review}</p>
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.key} className="flex items-center gap-2">
                <input type="checkbox" aria-label={t.receipt.include(r.name)} checked={r.include} onChange={(e) => update(r.key, { include: e.target.checked })} />
                <input aria-label={t.receipt.itemName} value={r.name} onChange={(e) => update(r.key, { name: e.target.value })}
                  className="min-h-11 min-w-0 flex-1 rounded-lg border border-slate-300 px-2 dark:border-slate-700 dark:bg-slate-900" />
                <input aria-label={t.receipt.itemPrice(r.name)} value={r.price} inputMode="decimal" onChange={(e) => update(r.key, { price: e.target.value })}
                  className="min-h-11 w-20 rounded-lg border border-slate-300 px-2 text-right dark:border-slate-700 dark:bg-slate-900" />
              </li>
            ))}
          </ul>
          <Button className="w-full" disabled={sending || selected === 0} onClick={submitAll}>
            {sending ? t.receipt.sending : t.receipt.submit(selected)}
          </Button>
        </>
      )}

      {summary && (
        <Notice tone={summary.failed ? "error" : "success"}>
          {t.receipt.summary(summary.accepted, summary.pending)}
          {summary.unmatched.length > 0 && <> {t.receipt.unmatched(summary.unmatched.join(", "))}</>}
          {summary.failed > 0 && <> {t.receipt.failed(summary.failed)}</>}
        </Notice>
      )}
    </Card>
  );
}

const rowPrice = (r: Row) => r.price.replace(",", ".");
